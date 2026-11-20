"""Serve the pinned BM25 + prior + LinUCB pipeline with durable decisions.

The algorithm implementations remain in app.ml. Only public card fields are
persisted in the serving receipt; model features and seed stay in event storage.
"""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.data_preparation.ranking_bundle import load_ranking_catalog, project_progress
from app.data_preparation.retrieval_bundle import verify_index
from app.data_preparation.history_io import resolve_bundle
from app.database.connection import events_engine, events_sessions
from app.ml.bm25_retriever import BM25Retriever
from app.ml.feature_registry import REGISTRY_HASH
from app.ml.hybrid_retrieval import DenseHybridRetriever
from app.ml.lsa_retriever import EMBEDDING_VERSION, LsaRetriever
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.profile_policy import fingerprint
from app.ml.prior_ranking import rank_candidates
from app.ml.ranking_inputs import from_hybrid
from app.ml.request_context import build_request_context
from app.ml.user_profile import build_user_profile
from app.models.learning import RewardObservation, RewardRevision
from app.models.serving import ServingRequest
from app.schemas.recommendation import (
    CatalogueRankItem, CatalogueRankRequest, CatalogueRankResponse, RecommendationCard, RecommendationResponse,
)
from app.services.event_service import EventConflict, EventService
from app.services.learning_configuration import DEMO_MODEL_KEY, learning_service
from app.services.recommendation_orchestrator import issue_recommendations
from app.services.recommendation_provider import ProviderUnavailable, RequestConflict

ROOT = Path(__file__).resolve().parents[3]


class _TransactionSessions:
    """Reuse the caller's transaction for existing ML services; never commit here."""
    def __init__(self, session):
        self.session = session

    @contextmanager
    def begin(self):
        yield self.session


class MLRecommendationProvider:
    def __init__(self, index, manifest, materials, engine, secret, *, demo=False, dense=None):
        self.index, self.manifest, self.materials = index, manifest, materials
        self.engine, self.sessions, self.secret = engine, events_sessions(engine), secret
        self.demo = demo
        self.model_key = DEMO_MODEL_KEY if demo else 'shared-linucb-v1'
        if demo and engine.url.database != 'alfa_events_test':
            raise ValueError('Fast demo requires isolated alfa_events_test')
        # Build the existing BM25 channel once from the verified public corpus.
        self.search = BM25Retriever().fit(list(index.materials.values()), index.rows)
        # Dense channel: verified vector dataset when the stack built one, or a
        # deterministic in-process fit for tests.  E5 can replace this encoder
        # without changing the fusion or ranking code.
        self.dense = dense or LsaRetriever(min_similarity=0.10).fit(
            list(index.materials.values()), index.rows)
        if self.dense.rows != index.rows:
            raise ValueError('Dense rows do not match the retrieval corpus')
        self.hybrid = DenseHybridRetriever(self.dense, self.search, dense_weight=0.4)
        self.retrieval_policy_id = fingerprint({
            'method': 'hybrid-bm25-dense', 'k1': self.search.k1, 'b': self.search.b,
            'coverage': self.search.min_query_coverage, 'analyzer': self.search.analyzer_version,
            'dense': EMBEDDING_VERSION, 'dense_dim': int(self.dense.vectors.shape[1]),
            'dense_weight': self.hybrid.dense_weight, 'dense_ratio': self.hybrid.dense_ratio,
        })
        self.retrieval_parameters = {'k1': self.search.k1, 'b': self.search.b,
                                     'coverage': self.search.min_query_coverage,
                                     'analyzer': self.search.analyzer_version,
                                     'dense': EMBEDDING_VERSION,
                                     'dense_dim': int(self.dense.vectors.shape[1]),
                                     'dense_weight': self.hybrid.dense_weight}
        self._model_cache = None
        self._ledger_version = None

    @classmethod
    def load(cls, settings):
        if not settings.session_secret or len(settings.session_secret.encode('utf-8')) < 32:
            raise ValueError('A stable session secret is required')
        catalog = Path(settings.catalog_dir)
        index = Path(settings.retrieval_index_dir)
        if not catalog.is_absolute(): catalog = ROOT / catalog
        if not index.is_absolute(): index = ROOT / index
        # Reconstruct from public catalog chunks and verify provenance once at startup.
        verified_manifest, _ = verify_index(index, catalog)
        search, manifest, materials = load_ranking_catalog(index, catalog)
        if verified_manifest['bundle_id'] != manifest['bundle_id']:
            raise ValueError('Retrieval index changed during startup')
        catalog_manifest = json.loads((resolve_bundle(catalog) / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('catalog_files') != catalog_manifest.get('files'):
            raise ValueError('Catalog/index checksums are incompatible')
        if manifest['catalog_bundle_id'] == '' or not REGISTRY_HASH:
            raise ValueError('Invalid catalog or feature registry')
        dense = None
        embedding_dir = getattr(settings, 'embedding_dir', None)
        if embedding_dir:
            path = Path(embedding_dir)
            if not path.is_absolute(): path = ROOT / path
            if (path / 'CURRENT').exists():
                dense = LsaRetriever.load(path)
                dense.attach_materials(materials)
                if dense.rows != search.rows:
                    raise ValueError('Dense dataset does not match the retrieval index')
        engine = events_engine()
        try:
            with engine.connect() as connection:
                revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                if revision != '0007_unattributed_clicks':
                    raise ValueError('Events database migrations are incompatible')
            return cls(search, manifest, materials, engine, settings.session_secret,
                       demo=settings.demo_fast_learning, dense=dense)
        except Exception:
            engine.dispose()
            raise

    def close(self):
        self.engine.dispose()

    def _request_hash(self, request):
        data = request.model_dump(mode='json', exclude={'request_key'})
        # A key issued in normal mode must not replay silently as a simulation,
        # or vice versa, even when the same test DB and actor are reused.
        # Keep the existing standard-mode hash unchanged for compatibility.
        if self.demo:
            data['learning_mode'] = 'test_fast'
        canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return hmac.new(self.secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()

    @staticmethod
    def _lock_request(db, actor, request_key):
        raw = hashlib.sha256(actor.actor_id.bytes + request_key.bytes).digest()[:8]
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int.from_bytes(raw, 'big', signed=True)})

    def _model(self, db):
        # Match the learner's advisory lock; ledger revision count changes on
        # each append. Cache stays immutable during ranking and refreshes on change.
        db.execute(text('SELECT pg_advisory_xact_lock(731987122)'))
        version = db.scalar(select(func.count()).select_from(RewardRevision).join(
            RewardObservation, RewardObservation.id == RewardRevision.observation_id
        ).where(RewardObservation.model_key == self.model_key))
        if self._model_cache is None or self._ledger_version != version:
            model = learning_service(_TransactionSessions(db), demo=self.demo, database_name=self.engine.url.database).replay()
            self._model_cache, self._ledger_version = model, version
        return self._model_cache

    def _bandit_preview(self, prior):
        """Return UCB scores for prior candidates without logging an impression.

        A cold LinUCB model has ``b == 0`` and cannot rank anything yet; in that
        state the preview keeps the prior order.  Once the shared demo model has
        observed rewards, its UCB values are blended inside a relevance guard.
        """
        if not prior.candidates:
            return {}, 'cold', 0
        try:
            with self.sessions.begin() as db:
                model = self._model(db)
                observations = int(self._ledger_version or 0)
                warm = observations > 0 and any(abs(value) > 1e-12 for value in model.b)
                scores = {
                    card.material_key: float(model.score(card.features.vector).total)
                    for card in prior.candidates
                }
            return scores, 'warm' if warm else 'cold', observations
        except Exception:
            return {}, 'unavailable', 0

    def rank_preview(self, request: CatalogueRankRequest) -> CatalogueRankResponse:
        """Rank the whole pinned catalogue for a profile without writing a decision.

        The retrieval batch is a weighted BM25 + dense-vector fusion.  Prior
        ranking is the same deterministic policy used for serving.  LinUCB is
        evaluated read-only and blended only when the shared model is warm; no
        impression, click or reward row is written here.
        """
        prefs = ExplicitPreferences(
            business_stage=request.profile.business_stage,
            industry=request.profile.industry,
            experience=request.profile.experience,
        )
        profile = build_user_profile(
            'anon:catalogue-preview', [], self.materials, prefs,
            catalog_bundle_id=self.manifest['catalog_bundle_id'],
        )
        constraints = ExplicitConstraints(
            formats=request.constraints.formats,
            budget_preference=request.constraints.budget_preference,
            available_time_minutes=request.constraints.available_time_minutes,
        )
        context = build_request_context(profile, request.task, constraints)
        progress = project_progress(profile, [])
        found = self.hybrid.query(context, 50)
        batch = from_hybrid(found, context,
            index_bundle_id=self.manifest['bundle_id'],
            catalog_bundle_id=self.manifest['catalog_bundle_id'],
            retrieval_policy_id=self.retrieval_policy_id,
            retrieval_parameters=self.retrieval_parameters)
        dense_scores = {
            key: channels['dense']['score']
            for key, _, channels in found if 'dense' in channels
        }
        blocked = {m.material_key for m in self.materials
                   if request.constraints.budget_preference == 'free_only'
                   and m.listed_price is not None and m.listed_price > 0}
        prior = rank_candidates(batch, self.materials, context, profile=profile,
                                progress=progress, blocked_material_keys=blocked, k=50)
        bandit_scores, bandit_state, observations = self._bandit_preview(prior)
        top_prior = max((card.prior_score for card in prior.candidates), default=0.0) or 1.0
        final_scores = {}
        for card in prior.candidates:
            final = card.prior_score / top_prior
            if bandit_state == 'warm' and bandit_scores:
                ordered = sorted(bandit_scores.values())
                low, high = ordered[0], ordered[-1]
                spread = high - low
                # Only candidates close to the best prior can be promoted.
                if spread > 1e-12 and card.prior_score >= 0.7 * top_prior:
                    ucb = (bandit_scores.get(card.material_key, low) - low) / spread
                    final = 0.85 * final + 0.15 * max(0.0, min(1.0, ucb))
            final_scores[card.material_key] = final
        ordered_cards = sorted(
            prior.candidates,
            key=lambda card: (-final_scores[card.material_key], card.rank, card.material_key),
        )
        ml_rank = {card.material_key: index for index, card in enumerate(ordered_cards, 1)}
        top_final = max(final_scores.values(), default=0.0) or 1.0
        ranked = {card.material_key: card for card in prior.candidates}
        items = []
        for material in self.materials:
            card = ranked.get(material.material_key)
            if card is None:
                fit_score = 0
                reason = 'ML-поиск не нашёл совпадений с этой формулировкой; материал остаётся в каталоге.'
                item_rank = None
            else:
                fit_score = max(0, min(100, round(100 * final_scores[material.material_key] / top_final)))
                texts = [part.text for part in card.reasons if part.text.strip()]
                if material.material_key in dense_scores:
                    texts.append(
                        'Векторная близость к запросу: '
                        f'{dense_scores[material.material_key]:.2f} (LSA-косинус; диагностика, не вероятность).'
                    )
                reason = ' '.join(texts[:3]) or 'Материал попал в выдачу по вашему профилю и задаче.'
                item_rank = ml_rank[material.material_key]
            items.append(CatalogueRankItem(
                material_key=material.material_key, title=material.title,
                format=material.item_type, duration_minutes=material.duration_minutes,
                listed_price=(Decimal(str(material.listed_price))
                              if material.listed_price is not None else None),
                fit_score=fit_score, ml_rank=item_rank, retrieved=card is not None,
                reason=reason[:1000],
                dense_score=dense_scores.get(material.material_key),
                bandit_score=bandit_scores.get(material.material_key),
            ))
        items.sort(key=lambda item: (-item.fit_score, item.ml_rank or 10_000, item.title))
        return CatalogueRankResponse(
            status=prior.status, items=items[:request.limit],
            message=prior.clarification if prior.status != 'matched' else None,
            algorithm='hybrid-bm25-dense-prior-linucb-v1',
            retrieval_method='hybrid-bm25-dense',
            dense_model=EMBEDDING_VERSION,
            dense_dimensions=int(self.dense.vectors.shape[1]),
            bandit_state=bandit_state,
            bandit_observations=observations,
        )

    def recommend(self, actor, request):
        request_hash = self._request_hash(request)
        try:
            with self.sessions.begin() as db:
                self._lock_request(db, actor, request.request_key)
                existing = db.get(ServingRequest, (actor.actor_id, request.request_key))
                if existing is not None:
                    if not hmac.compare_digest(existing.request_hash, request_hash):
                        raise RequestConflict()
                    return RecommendationResponse.model_validate(existing.response)
                prefs = ExplicitPreferences(
                    business_stage=request.profile.business_stage,
                    industry=request.profile.industry,
                    experience=request.profile.experience,
                )
                profile = build_user_profile(
                    f'anon:{actor.actor_id}', [], self.materials, prefs,
                    catalog_bundle_id=self.manifest['catalog_bundle_id'],
                )
                constraints = ExplicitConstraints(
                    formats=request.constraints.formats,
                    budget_preference=request.constraints.budget_preference,
                    available_time_minutes=request.constraints.available_time_minutes,
                )
                context = build_request_context(profile, request.task, constraints)
                progress = project_progress(profile, [])
                found = self.hybrid.query(context, 50)
                batch = from_hybrid(found, context,
                    index_bundle_id=self.manifest['bundle_id'],
                    catalog_bundle_id=self.manifest['catalog_bundle_id'],
                    retrieval_policy_id=self.retrieval_policy_id,
                    retrieval_parameters=self.retrieval_parameters)
                blocked = {m.material_key for m in self.materials
                           if request.constraints.budget_preference == 'free_only'
                           and m.listed_price is not None and m.listed_price > 0}
                prior = rank_candidates(batch, self.materials, context, profile=profile,
                                        progress=progress, blocked_material_keys=blocked, k=50)
                result = issue_recommendations(EventService(_TransactionSessions(db)), actor,
                    request.request_key, prior, context, batch, lambda: self._model(db), k=request.limit, simulated=self.demo)
                decision, selected = result['decision'], result['result']
                refs = decision['items']
                if len(refs) != len(selected) or any(
                    item['material_key'] != card.material_key or item['position'] != pos
                    for pos, (item, card) in enumerate(zip(refs, selected), 1)
                ):
                    raise ValueError('Issued items do not match selected cards')
                cards = []
                for item, card in zip(refs, selected):
                    reasons = [r.text for r in card.reasons if r.text.strip()]
                    reason = ' '.join(reasons[1:] or reasons[:1])
                    cards.append(RecommendationCard(
                        item_id=item['item_id'], material_key=card.material_key,
                        position=item['position'], title=card.title, format=card.item_type,
                        url=card.url, link_status='reachable' if card.url_state == 'reachable' else 'unknown',
                        access_type=card.access_type or None, requires_access_check=card.requires_access_check,
                        listed_price=(Decimal(str(card.listed_price)) if card.listed_price is not None
                                      and not (card.listed_price == 0 and card.access_type != 'Открытый') else None),
                        duration_minutes=card.duration_minutes, reason=reason,
                    ))
                message = prior.clarification if not cards else None
                if cards and result['fallback_reason']:
                    message = 'Временно использовано базовое ранжирование.'
                elif cards and len(cards) < request.limit:
                    message = 'Найдены не все запрошенные материалы. Попробуйте уточнить задачу.'
                public = RecommendationResponse(learning_mode='test_fast' if self.demo else 'standard', status=prior.status, decision_id=decision['decision_id'],
                                                items=cards, message=message)
                db.add(ServingRequest(actor_id=actor.actor_id, request_key=request.request_key,
                    request_hash=request_hash, decision_id=public.decision_id,
                    response=public.model_dump(mode='json')))
                db.flush()
                return public
        except RequestConflict:
            raise
        except (SQLAlchemyError, EventConflict, ValueError, OSError, ArithmeticError, KeyError, TypeError) as exc:
            raise ProviderUnavailable() from exc
