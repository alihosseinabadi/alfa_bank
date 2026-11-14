"""Pure adapters for existing TF-IDF, BM25, E5 and fused retrieval interfaces."""
from .ranking_contracts import RetrievalBatch, RetrievalHit, ChannelEvidence

def _batch(context, hits, *, index_bundle_id, catalog_bundle_id, retrieval_policy_id, method,
           status=None, clarification=None, retrieval_parameters=None):
    status = status or ("matched" if hits else "needs_clarification")
    return RetrievalBatch(context_id=context.context_id, index_bundle_id=index_bundle_id,
        catalog_bundle_id=catalog_bundle_id, retrieval_policy_id=retrieval_policy_id,
        method=method, status=status, hits=hits, retrieval_parameters=retrieval_parameters or {},
        clarification=clarification if hits else clarification or "Уточните задачу или измените ограничения.")

def from_search_result(result, chunks_by_id, context, **provenance):
    from .retrieval_contracts import RETRIEVAL_VERSION
    if result.version != RETRIEVAL_VERSION or result.context_id != context.context_id:
        raise ValueError("Retrieval/context mismatch")
    hits = []
    for rank, candidate in enumerate(result.candidates, 1):
        chunk = chunks_by_id[candidate.evidence_chunk_id]
        hits.append(RetrievalHit(material_key=candidate.material_key, retrieval_rank=rank,
            raw_score=candidate.retrieval_score, evidence=[ChannelEvidence(channel=result.algorithm,
                raw_score=candidate.retrieval_score, channel_rank=rank, chunk=chunk)]))
    return _batch(context, hits, method=result.algorithm, status=result.status,
                  clarification=result.clarification, **provenance)

def from_channel(rows, context, *, method, **provenance):
    if method not in {"bm25", "e5"}:
        raise ValueError("Unsupported single retrieval channel")
    hits = [RetrievalHit(material_key=key, retrieval_rank=rank, raw_score=score,
        evidence=[ChannelEvidence(channel=method, raw_score=score, channel_rank=rank, chunk=chunk)])
        for rank, (key, score, chunk) in enumerate(rows, 1)]
    return _batch(context, hits, method=method, **provenance)

def from_hybrid(rows, context, **provenance):
    hits = []
    for rank, (key, score, channels) in enumerate(rows, 1):
        evidence = []
        for name in sorted(channels):
            canonical = {"semantic": "e5", "lexical": "bm25"}.get(name)
            if canonical is None:
                raise ValueError("Unknown hybrid channel")
            item = channels[name]
            evidence.append(ChannelEvidence(channel=canonical, raw_score=item["score"],
                channel_rank=item["rank"], chunk=item["chunk"]))
        hits.append(RetrievalHit(material_key=key, retrieval_rank=rank, raw_score=score, evidence=evidence))
    return _batch(context, hits, method="hybrid", **provenance)
