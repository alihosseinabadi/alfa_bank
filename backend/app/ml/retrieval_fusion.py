"""Deterministic fusion for independently filtered retrieval channels."""
import math


def _validate(channels, k, weights):
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("Invalid fusion limit")
    weights = weights or {name: 1.0 for name in channels}
    if set(weights) != set(channels) or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Invalid channel weights")
    return weights


def reciprocal_rank_fusion(channels, k=50, rank_constant=60, weights=None):
    if not math.isfinite(rank_constant) or rank_constant <= 0:
        raise ValueError("Invalid fusion limits")
    weights = _validate(channels, k, weights)
    totals, evidence = {}, {}
    for name in sorted(channels):
        if weights[name] == 0:
            continue
        seen = set()
        for rank, (key, score, chunk) in enumerate(channels[name], 1):
            if key in seen:
                raise ValueError("Duplicate material in channel")
            if not math.isfinite(score) or chunk.material_key != key:
                raise ValueError("Invalid channel evidence")
            seen.add(key)
            totals[key] = totals.get(key, 0.0) + weights[name] / (rank_constant + rank)
            evidence.setdefault(key, {})[name] = {"rank": rank, "score": float(score), "chunk": chunk}
    return [(key, totals[key], evidence[key]) for key in sorted(totals, key=lambda key: (-totals[key], key))[:min(k, 50)]]


def normalized_score_fusion(channels, k=50, weights=None):
    """Convex combination of per-channel scores scaled to their own maximum.

    BM25 scores are unbounded and cosine similarities live in [-1, 1], so the
    raw numbers cannot be added. Each channel is divided by its best score for
    this query, then the channels are weighted. The result keeps the original
    channel evidence, including the unnormalised score, for explanations.
    """
    weights = _validate(channels, k, weights)
    totals, evidence = {}, {}
    for name in sorted(channels):
        rows = channels[name]
        if weights[name] == 0 or not rows:
            continue
        top = max(score for _, score, _ in rows)
        if not math.isfinite(top) or top <= 0:
            continue
        seen = set()
        for rank, (key, score, chunk) in enumerate(rows, 1):
            if key in seen:
                raise ValueError("Duplicate material in channel")
            if not math.isfinite(score) or chunk.material_key != key:
                raise ValueError("Invalid channel evidence")
            seen.add(key)
            totals[key] = totals.get(key, 0.0) + weights[name] * (score / top)
            evidence.setdefault(key, {})[name] = {"rank": rank, "score": float(score), "chunk": chunk}
    return [(key, totals[key], evidence[key]) for key in sorted(totals, key=lambda key: (-totals[key], key))[:min(k, 50)]]