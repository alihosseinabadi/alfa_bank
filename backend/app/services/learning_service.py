"""Serialized reward projection from immutable events to a replayable ledger."""
from datetime import datetime, timezone
import hashlib, json
from uuid import uuid4
from sqlalchemy import select, text
from app.models.events import Decision, DecisionItem, Impression, Interaction
from app.models.learning import RewardObservation, RewardRevision
from app.ml.feature_registry import REGISTRY_HASH, FEATURE_DIMENSION, validate_features
from app.ml.ranking_contracts import PairFeatures
from app.ml.reward_policy import RewardPolicy
from app.ml.linucb import SharedLinUCB

class LearningService:
    def __init__(self, sessions, model_key='shared-linucb-v1', policy=None, ridge=1.0, alpha=0.5):
        self.sessions, self.model_key = sessions, model_key
        self.policy, self.ridge, self.alpha = policy or RewardPolicy(), ridge, alpha
        SharedLinUCB(FEATURE_DIMENSION, ridge, alpha)
        self.identity = hashlib.sha256(json.dumps([self.policy.fingerprint, REGISTRY_HASH, ridge, alpha], separators=(chr(44), chr(58))).encode()).hexdigest()

    def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None: raise ValueError('timezone required')
        changed = 0
        with self.sessions.begin() as db:
            db.execute(text('SELECT pg_advisory_xact_lock(731987122)'))
            rows = db.execute(select(Impression, DecisionItem, Decision).join(DecisionItem, Impression.item_id == DecisionItem.id).join(Decision, DecisionItem.decision_id == Decision.id).where(Decision.simulated == False).order_by(Impression.id)).all()
            for impression, item, decision in rows:
                events = db.scalars(select(Interaction).where(Interaction.impression_id == impression.id, Interaction.item_id == item.id, Interaction.actor_id == decision.actor_id)).all()
                if any(e.is_free_open and item.access_type != 'Открытый' for e in events): raise ValueError('inconsistent free access')
                reward = self.policy.reward(impression, events, now)
                if reward is None: continue
                features = PairFeatures.model_validate(item.snapshot['features'])
                validate_features(features)
                if features.material_key != item.material_key: raise ValueError('feature material mismatch')
                meta = decision.snapshot['metadata']
                if any(getattr(features, k) != meta[k] for k in ('context_id','profile_version','catalog_bundle_id','index_bundle_id','retrieval_policy_id')):
                    raise ValueError('feature decision provenance mismatch')
                obs = db.scalar(select(RewardObservation).where(RewardObservation.model_key == self.model_key, RewardObservation.impression_id == impression.id))
                if obs is None:
                    obs = RewardObservation(id=uuid4(), impression_id=impression.id, model_key=self.model_key, registry_hash=REGISTRY_HASH, policy_hash=self.identity, features=features.vector, reward=reward, revision=1, updated_at=now)
                    db.add(obs)
                    db.flush()
                    old = None
                else:
                    if obs.registry_hash != REGISTRY_HASH or obs.policy_hash != self.identity or obs.features != features.vector:
                        raise ValueError('incompatible observation provenance')
                    if now < obs.updated_at: raise ValueError('observation clock moved backwards')
                    if obs.reward == reward: continue
                    old = obs.reward
                    obs.reward, obs.revision, obs.updated_at = reward, obs.revision + 1, now
                db.add(RewardRevision(observation_id=obs.id, revision=obs.revision, old_reward=old, new_reward=reward, recorded_at=now))
                changed += 1
        return changed

    def replay(self):
        model = SharedLinUCB(FEATURE_DIMENSION, self.ridge, self.alpha)
        prefix = []
        with self.sessions.begin() as db:
            db.execute(text('SELECT pg_advisory_xact_lock(731987122)'))
            observations = db.scalars(select(RewardObservation).where(RewardObservation.model_key == self.model_key).order_by(RewardObservation.impression_id)).all()
            for obs in observations:
                if obs.registry_hash != REGISTRY_HASH or obs.policy_hash != self.identity:
                    raise ValueError('incompatible observation provenance')
                revisions = db.scalars(select(RewardRevision).where(RewardRevision.observation_id == obs.id).order_by(RewardRevision.revision)).all()
                if not revisions or len(revisions) != obs.revision: raise ValueError('incomplete ledger')
                prev = None
                for n, rev in enumerate(revisions, 1):
                    if rev.revision != n or rev.old_reward != prev: raise ValueError('broken revision chain')
                    if n == 1: model.observe(obs.features, rev.new_reward)
                    else: model.revise(obs.features, prev, rev.new_reward)
                    prev = rev.new_reward
                if prev != obs.reward: raise ValueError('ledger projection mismatch')
                prefix.append([str(obs.impression_id), obs.features, [[r.revision, r.old_reward, r.new_reward] for r in revisions]])
        model.state_id = hashlib.sha256(json.dumps([self.identity, prefix], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        model.matrix_digest = model.state_digest()
        return model
