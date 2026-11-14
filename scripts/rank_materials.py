"""Task/profile -> retrieval top50 -> observable pair features -> prior top6."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.profile_policy import fingerprint
from app.ml.prior_ranking import PriorPolicy, rank_candidates
from app.ml.ranking_inputs import from_search_result, from_channel, from_hybrid
from app.ml.feature_registry import registry_document
from app.data_preparation.ranking_bundle import load_ranking_catalog, load_ranking_context, save_ranking

def retrieve_batch(index, manifest, context, args):
    provenance = dict(index_bundle_id=manifest["bundle_id"], catalog_bundle_id=manifest["catalog_bundle_id"])
    if args.method == "tfidf":
        policy_id = fingerprint({"method": "tfidf", "version": "tfidf-search-v1", "policy": index.policy.model_dump()})
        return from_search_result(index.query(context, 50), {r.chunk_id: r for r in index.rows}, context,
                                  retrieval_policy_id=policy_id,
                                  retrieval_parameters={"min_similarity": index.policy.min_similarity,
                                      "coverage": index.policy.min_query_coverage, "ngram_max": index.policy.ngram_max}, **provenance)
    from app.ml.bm25_retriever import BM25Retriever
    lexical = BM25Retriever().fit(list(index.materials.values()), index.rows)
    if args.method == "bm25":
        return from_channel(lexical.query(context, 50), context, method="bm25",
            retrieval_policy_id=fingerprint({"method": "bm25", "k1": lexical.k1, "b": lexical.b,
                                             "coverage": lexical.min_query_coverage}),
            retrieval_parameters={"k1": lexical.k1, "b": lexical.b, "coverage": lexical.min_query_coverage}, **provenance)
    if args.semantic_threshold is None:
        raise ValueError("E5/hybrid require an explicit --semantic-threshold; it is not calibrated")
    from app.ml.e5_retriever import LocalE5Encoder
    from app.ml.hybrid_retriever import HybridRetriever
    from app.data_preparation.e5_bundle import load_e5_vectors
    if not (args.model_dir / "model.safetensors").exists() or not (args.vector_dir / "manifest.json").exists():
        raise FileNotFoundError("Local E5 model/vectors are absent. Supply --model-dir and --vector-dir or use --method tfidf.")
    import torch
    torch.set_num_threads(4)
    encoder = LocalE5Encoder(args.model_dir)
    semantic, vectors = load_e5_vectors(index, manifest, encoder, args.vector_dir)
    params = {"method": args.method, "threshold": args.semantic_threshold,
        "e5_identity": vectors["identity"], "vectors_sha256": vectors["vectors_sha256"],
        "coverage": lexical.min_query_coverage, "rrf_constant": 60}
    policy_id = fingerprint(params)
    provenance["retrieval_parameters"] = {"semantic_threshold": args.semantic_threshold,
        "model_revision": vectors["identity"]["revision"], "vectors_sha256": vectors["vectors_sha256"],
        "coverage": lexical.min_query_coverage, "k1": lexical.k1, "b": lexical.b, "rrf_constant": 60}
    if args.method == "e5":
        # Apply the same conservative vocabulary gate as the experimental hybrid.
        from app.ml.tfidf_retriever import tokenize_text
        terms = set(tokenize_text(context.query_text))
        covered = terms and sum(t in lexical.postings for t in terms) / len(terms) >= lexical.min_query_coverage
        rows = [r for r in semantic.query(context, 50) if r[1] >= args.semantic_threshold] if covered else []
        return from_channel(rows, context, method="e5", retrieval_policy_id=policy_id, **provenance)
    rows = HybridRetriever(semantic, lexical, semantic_threshold=args.semantic_threshold).query(context, 50)
    return from_hybrid(rows, context, retrieval_policy_id=policy_id, **provenance)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", default="")
    p.add_argument("--method", choices=["tfidf", "bm25", "e5", "hybrid"], default="tfidf")
    p.add_argument("--formats", nargs="*", choices=["course", "article", "document", "webinar", "podcast", "glossary", "calculator"])
    p.add_argument("--time-minutes", type=int)
    p.add_argument("--free-only", action="store_true")
    p.add_argument("--topics", nargs="*")
    p.add_argument("--industry")
    p.add_argument("--user-key", help="Private local profile; not printed")
    p.add_argument("--k", type=int, default=6)
    p.add_argument("--policy", type=Path)
    p.add_argument("--semantic-threshold", type=float)
    p.add_argument("--index-dir", type=Path, default=ROOT / "artifacts/retrieval")
    p.add_argument("--catalog-dir", type=Path, default=ROOT / "data/processed/catalog")
    p.add_argument("--profiles-dir", type=Path, default=ROOT / "data/processed/profiles")
    p.add_argument("--history-dir", type=Path, default=ROOT / "data/processed/history")
    p.add_argument("--model-dir", type=Path, default=ROOT / "artifacts/e5-model")
    p.add_argument("--vector-dir", type=Path, default=ROOT / "artifacts/e5-vectors")
    p.add_argument("--output-dir", type=Path, help="Private ignored artifact directory")
    p.add_argument("--include-features", action="store_true")
    p.add_argument("--export-registry", action="store_true")
    args = p.parse_args()
    if args.export_registry:
        print(json.dumps(registry_document(), ensure_ascii=False, indent=2))
        return
    if args.k < 1:
        p.error("--k must be positive")
    if args.semantic_threshold is not None and not -1 <= args.semantic_threshold <= 1:
        p.error("--semantic-threshold must be finite and between -1 and 1")
    policy = PriorPolicy.model_validate_json(args.policy.read_text()) if args.policy else PriorPolicy()
    index, manifest, materials = load_ranking_catalog(args.index_dir, args.catalog_dir)
    prefs = ExplicitPreferences(selected_topics=args.topics or [], industry=args.industry) if args.topics is not None or args.industry else None
    profile, context, progress = load_ranking_context(materials, manifest, args.task,
        ExplicitConstraints(formats=args.formats, available_time_minutes=args.time_minutes,
                            budget_preference="free_only" if args.free_only else None),
        user_key=args.user_key, profiles_dir=args.profiles_dir, history_dir=args.history_dir,
        explicit_preferences=prefs)
    batch = retrieve_batch(index, manifest, context, args)
    result = rank_candidates(batch, materials, context, profile=profile, progress=progress, policy=policy, k=args.k)
    if args.output_dir:
        output = args.output_dir.resolve()
        allowed = [(ROOT / name).resolve() for name in ("artifacts", "data/processed", "reports")]
        if not any(output.is_relative_to(base) for base in allowed):
            p.error("--output-dir must be under private ignored artifacts, data/processed or reports")
        save_ranking(result, policy, output, ROOT)
    payload = result.model_dump()
    if not args.include_features:
        for card in payload["candidates"]:
            card.pop("features")
            card.pop("score_components")
    payload["continuation_candidates"] = [{"requires_access_check": True, "requires_progression_check": True,
        "candidate_count": len(c.candidate_lesson_ids)} for c in result.continuation_candidates]
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
