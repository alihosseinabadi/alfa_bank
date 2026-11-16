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
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.profile_policy import fingerprint
from app.ml.prior_ranking import rank_candidates
from app.ml.ranking_inputs import from_channel
from app.ml.request_context import build_request_context
from app.ml.user_profile import build_user_profile
from app.models.learning import RewardObservation, RewardRevision
from app.models.serving import ServingRequest
from app.schemas.recommendation import RecommendationCard, RecommendationResponse
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
    def __init__(self, index, manifest, materials, engine, secret, *, demo=False):
        self.index, self.manifest, self.materials = index, manifest, materials
        self.engine, self.sessions, self.secret = engine, events_sessions(engine), secret
        self.demo = demo
        self.model_key = DEMO_MODEL_KEY if demo else 'shared-linucb-v1'
        if demo and engine.url.database != 'alfa_events_test':
            raise ValueError('Fast demo requires isolated alfa_events_test')
        # Build the existing BM25 channel once from the verified public corpus.
        self.search = BM25Retriever().fit(list(index.materials.values()), index.rows)
        self.retrieval_policy_id = fingerprint({'method': 'bm25', 'k1': self.search.k1,
                                                'b': self.search.b, 'coverage': self.search.min_query_coverage})
        self.retrieval_parameters = {'k1': self.search.k1, 'b': self.search.b,
                                     'coverage': self.search.min_query_coverage}
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
        engine = events_engine()
        try:
            with engine.connect() as connection:
                revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                if revision != '0006_reward_projection':
                    raise ValueError('Events database migrations are incompatible')
            return cls(search, manifest, materials, engine, settings.session_secret, demo=settings.demo_fast_learning)
        except Exception:
            engine.dispose()
            raise

    def close(self):
        self.engine.dispose()

    def _request_hash(self, request):
        data = request.model_dump(mode='json', exclude={'request_key'})
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
                found = self.search.query(context, 50)
                batch = from_channel(found, context, method='bm25', materials=self.index.materials.values(),
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
