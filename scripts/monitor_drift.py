"""Drift monitor: retrieval coverage, no-match rate, CTR by position and channel.

Reads two JSONL streams and reports the four quantities that tell you a retrieval or
ranking change is degrading in production:

1. **no-match rate** — share of retrieval calls that returned no candidates. A rise
   means users are asking things the index cannot answer (or the guard is too strict).
2. **retrieval coverage** — share of calls with ``status == "matched"``, plus mean
   candidate count. A fall means fewer choices reach the ranker.
3. **CTR by position bucket** — 1-3 / 4-10 / 11+; a hard drop at a bucket boundary
   usually means the slate or the UI changed.
4. **CTR by channel** — per ``algorithm`` value, so a new retriever can be compared
   with the incumbent on the same traffic.

Expected record shapes (one JSON object per line)::

    retrieval: {"ts": "...", "context_id": "c1", "query": "...",
                "algorithm": "light_hybrid", "status": "matched",
                "candidates": [{"material_key": "m1", "rank": 1, "score": 0.7}]}

    events:    {"ts": "...", "context_id": "c1", "material_key": "m1",
                "kind": "click", "rank": 1, "channel": "light_hybrid"}

``kind`` values used here: ``impression`` and any positive interaction
(``click``, ``open``, ``inspect``, ``favorite``, ``lesson_start``). Everything else is
ignored so new event kinds cannot silently change the denominator.

This runs on exported files rather than the database on purpose: it must not need
credentials, and it can be pointed at a staging export before a rollout.

Usage:
    python scripts/monitor_drift.py --retrieval retrieval.jsonl --events events.jsonl
    python scripts/monitor_drift.py --retrieval r.jsonl --events e.jsonl --json out.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

POSITIVE_KINDS = frozenset({"click", "open", "inspect", "favorite", "lesson_start"})
IMPRESSION_KIND = "impression"
POSITION_BUCKETS = ((1, 3, "1-3"), (4, 10, "4-10"), (11, 10**9, "11+"))
NO_MATCH_STATUSES = frozenset({"no_eligible", "needs_clarification"})


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"{path}:{number} is not valid JSON") from exc
    return rows


def _bucket(rank: int | None) -> str:
    if rank is None:
        return "unknown"
    for low, high, name in POSITION_BUCKETS:
        if low <= rank <= high:
            return name
    return "unknown"


def retrieval_summary(retrieval: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    by_status: Counter[str] = Counter()
    by_algorithm: Counter[str] = Counter()
    candidate_counts: list[int] = []
    empty = 0
    for row in retrieval:
        total += 1
        status = row.get("status", "unknown")
        by_status[status] += 1
        by_algorithm[row.get("algorithm", "unknown")] += 1
        candidates = row.get("candidates") or []
        candidate_counts.append(len(candidates))
        if status in NO_MATCH_STATUSES or not candidates:
            empty += 1
    if total == 0:
        return {"calls": 0}
    return {
        "calls": total,
        "by_status": dict(sorted(by_status.items())),
        "by_algorithm": dict(sorted(by_algorithm.items())),
        "no_match_rate": round(empty / total, 4),
        "coverage": round(1.0 - empty / total, 4),
        "mean_candidates": round(sum(candidate_counts) / total, 2),
        "empty_calls": empty,
    }


def interaction_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    impressions: Counter[str] = Counter()          # key -> count
    positives: Counter[str] = Counter()
    position_impressions: Counter[str] = Counter()
    position_positives: Counter[str] = Counter()
    channel_impressions: Counter[str] = Counter()
    channel_positives: Counter[str] = Counter()
    impressions_by_context: dict[str, set[str]] = defaultdict(set)
    positives_by_context: dict[str, set[str]] = defaultdict(set)
    ignored: Counter[str] = Counter()

    for row in events:
        kind = row.get("kind")
        context_id = row.get("context_id")
        material_key = row.get("material_key")
        if kind is None or context_id is None or material_key is None:
            ignored["malformed"] += 1
            continue
        if kind == IMPRESSION_KIND:
            impressions[(context_id, material_key)] += 1
            position_impressions[_bucket(row.get("rank"))] += 1
            channel_impressions[row.get("channel", "unknown")] += 1
            impressions_by_context[context_id].add(material_key)
        elif kind in POSITIVE_KINDS:
            positives[(context_id, material_key)] += 1
            position_positives[_bucket(row.get("rank"))] += 1
            channel_positives[row.get("channel", "unknown")] += 1
            positives_by_context[context_id].add(material_key)
        else:
            ignored[kind] += 1

    total_impressions = sum(impressions.values())
    total_positives = sum(positives.values())

    def rate(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    return {
        "impressions": total_impressions,
        "positives": total_positives,
        "ctr": rate(total_positives, total_impressions),
        "ctr_by_position": {
            name: {
                "impressions": position_impressions[name],
                "positives": position_positives[name],
                "ctr": rate(position_positives[name], position_impressions[name]),
            }
            for _, _, name in POSITION_BUCKETS
            if position_impressions[name]
        },
        "ctr_by_channel": {
            channel: {
                "impressions": count,
                "positives": channel_positives[channel],
                "ctr": rate(channel_positives[channel], count),
            }
            for channel, count in sorted(channel_impressions.items())
        },
        "contexts_with_impressions": len(impressions_by_context),
        "contexts_with_positive": len(positives_by_context),
        "ignored_kinds": dict(sorted(ignored.items())),
    }


def monitor(retrieval: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "retrieval": retrieval_summary(retrieval),
        "interactions": interaction_summary(events),
    }


def markdown(report: dict[str, Any]) -> str:
    retrieval = report["retrieval"]
    interactions = report["interactions"]
    lines = ["| metric | value |", "|---|---|"]
    if retrieval.get("calls"):
        lines += [
            f"| retrieval calls | {retrieval['calls']} |",
            f"| no-match rate | {retrieval['no_match_rate']:.3f} |",
            f"| coverage | {retrieval['coverage']:.3f} |",
            f"| mean candidates | {retrieval['mean_candidates']} |",
            f"| status mix | {retrieval['by_status']} |",
            f"| algorithms | {retrieval['by_algorithm']} |",
        ]
    lines.append(f"| impressions / positives | {interactions['impressions']} / {interactions['positives']} |")
    lines.append(f"| CTR | {interactions['ctr']} |")
    if interactions["ctr_by_position"]:
        lines.append("")
        lines.append("| position | impressions | positives | CTR |")
        lines.append("|---|---|---|---|")
        for name, block in interactions["ctr_by_position"].items():
            lines.append(f"| {name} | {block['impressions']} | {block['positives']} | {block['ctr']} |")
    if interactions["ctr_by_channel"]:
        lines.append("")
        lines.append("| channel | impressions | positives | CTR |")
        lines.append("|---|---|---|---|")
        for name, block in interactions["ctr_by_channel"].items():
            lines.append(f"| {name} | {block['impressions']} | {block['positives']} | {block['ctr']} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    report = monitor(_read_jsonl(args.retrieval), _read_jsonl(args.events))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    print(markdown(report))


if __name__ == "__main__":
    main()
