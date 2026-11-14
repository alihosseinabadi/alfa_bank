"""Versioned, bounded reward rules. Server receipt time is authoritative."""
from dataclasses import dataclass, asdict
from datetime import timedelta
import hashlib
import json

@dataclass(frozen=True)
class RewardPolicy:
    version: str = 'reward-v1'
    maturity_seconds: int = 86400
    attribution_seconds: int = 604800
    click: float = 0.1
    free_open: float = 0.15
    confirmed_purchase: float = 1.0
    allow_verified_payments: bool = False

    def __post_init__(self):
        if self.maturity_seconds <= 0 or self.attribution_seconds < self.maturity_seconds:
            raise ValueError('invalid observation windows')
        if not 0 <= self.click <= self.free_open <= self.confirmed_purchase <= 1:
            raise ValueError('invalid reward ordering')

    @property
    def fingerprint(self):
        raw = json.dumps(asdict(self), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(raw.encode()).hexdigest()

    def reward(self, impression, events, now):
        if now.tzinfo is None or impression.confirmed_at.tzinfo is None:
            raise ValueError('timezone required')
        if now < impression.confirmed_at + timedelta(seconds=self.maturity_seconds):
            return None
        end = impression.confirmed_at + timedelta(seconds=self.attribution_seconds)
        reward = 0.0
        for event in events:
            if event.simulated or event.impression_id != impression.id or event.item_id != impression.item_id:
                continue
            if not impression.confirmed_at <= event.ingested_at <= now:
                continue
            if event.kind in ('click', 'material_open'):
                if event.source != 'client' or event.trust != 'client_reported' or event.ingested_at > end:
                    continue
                if event.kind == 'click': reward = max(reward, self.click)
                if event.kind == 'material_open' and event.is_free_open: reward = max(reward, self.free_open)
            elif event.kind == 'purchase_confirmed':
                if (self.allow_verified_payments and event.source == 'payment_server' and event.trust == 'server_verified'
                    and event.payment_environment == 'production' and event.client_time is not None
                    and impression.confirmed_at <= event.client_time <= min(end, now)):
                    reward = max(reward, self.confirmed_purchase)
        return reward
