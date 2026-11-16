"""Explicitly isolated simulated fast learning; real reward policy is unchanged."""
from dataclasses import dataclass
from types import SimpleNamespace

from app.ml.reward_policy import RewardPolicy
from app.services.learning_service import LearningService

DEMO_MODEL_KEY = 'demo-fast-linucb-v1'


@dataclass(frozen=True)
class DemoRewardPolicy(RewardPolicy):
    version: str = 'demo-fast-reward-v1'
    maturity_seconds: int = 2
    attribution_seconds: int = 86400

    def reward(self, impression, events, now):
        # Only simulated client events may enter this isolated test model.
        # Purchases are never counted in the demo, even test payment notices.
        allowed = []
        for event in events:
            if not event.simulated or event.kind not in {'click', 'material_open'}:
                continue
            allowed.append(SimpleNamespace(
                simulated=False, impression_id=event.impression_id, item_id=event.item_id,
                ingested_at=event.ingested_at, kind=event.kind, source=event.source,
                trust=event.trust, is_free_open=event.is_free_open,
            ))
        return super().reward(impression, allowed, now)


def learning_service(sessions, *, demo=False, database_name=None):
    if demo:
        if database_name != 'alfa_events_test':
            raise ValueError('Fast demo learning requires isolated alfa_events_test')
        return LearningService(sessions, model_key=DEMO_MODEL_KEY,
                               policy=DemoRewardPolicy(), simulated_only=True)
    return LearningService(sessions)
