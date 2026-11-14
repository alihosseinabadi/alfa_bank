"""UCB reranking operates only on the already eligible prior candidate slate."""
import hashlib
from .ranking_contracts import UCBRankedMaterial, UCBRankingResult
from .feature_registry import REGISTRY_HASH, FEATURE_DIMENSION, validate_features

def rank_ucb(prior, model, model_state_id):
    if prior.feature_registry_hash != REGISTRY_HASH or model.dimension != FEATURE_DIMENSION:
        raise ValueError('incompatible registry or model')
    if not model_state_id or model_state_id != getattr(model, 'state_id', None):
        raise ValueError('model state provenance required')
    if model.state_digest() != getattr(model, 'matrix_digest', None):
        raise ValueError('model state has changed')
    ranked = []
    for card in prior.candidates:
        validate_features(card.features)
        score = model.score(card.features.vector)
        ranked.append((card, score))
    ranked.sort(key=lambda pair: (-pair[1].total, pair[0].retrieval_rank, pair[0].material_key))
    cards = []
    for n, (card, score) in enumerate(ranked, 1):
        data = card.model_dump()
        data.update(rank=n, exploit=score.exploit, explore=score.explore, ucb_score=score.total)
        cards.append(UCBRankedMaterial.model_validate(data))
    data = prior.model_dump()
    data.update(version='shared-linucb-ranking-v1', model_state_id=model_state_id, candidates=cards)
    return UCBRankingResult.model_validate(data)

def rank_with_fallback(prior, model_loader):
    """Return (result, fallback reason); never fabricate a probability."""
    try:
        model = model_loader()
        return rank_ucb(prior, model, model.state_id), None
    except (ValueError, OSError, ArithmeticError, KeyError, TypeError) as exc:
        return prior, type(exc).__name__
