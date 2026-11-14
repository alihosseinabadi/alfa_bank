"""Deterministic reciprocal-rank fusion for independently filtered channels."""
import math

def reciprocal_rank_fusion(channels, k=50, rank_constant=60, weights=None):
    if not isinstance(k, int) or isinstance(k, bool) or k < 1 or not math.isfinite(rank_constant) or rank_constant <= 0:
        raise ValueError("Invalid fusion limits")
    weights = weights or {name: 1.0 for name in channels}
    if set(weights) != set(channels) or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Invalid channel weights")
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