"""Simple topic/tag overlap baseline sharing the same candidate eligibility."""
from .tfidf_retriever import tokenize_text,make_candidate
from .retrieval_contracts import SearchResult

def topic_baseline(index,context,k=50):
    if not isinstance(k,int) or isinstance(k,bool) or k<1:raise ValueError("k must be positive")
    k=min(k,index.policy.max_candidates,50)
    eligible=index._eligible(context)
    query=set(tokenize_text(context.query_text))
    if not eligible:return index._fallback(context,k,eligible,"topic_baseline","empty_eligible_pool")
    if not query:return index._fallback(context,k,eligible,"topic_baseline","empty_query")
    scores={}
    for key in eligible:
        material=index.materials[key]
        labels=set(tokenize_text(" ".join(material.topics+material.tags)))
        overlap=query&labels
        if overlap:scores[key]=len(overlap)/len(query|labels)
    ordered=sorted(scores,key=lambda key:(-scores[key],key))[:k]
    if not ordered:return index._fallback(context,k,eligible,"topic_baseline","no_topic_overlap")
    candidates=[make_candidate(index.materials[key],index._metadata_row(key),scores[key],context,"topic_baseline",query) for key in ordered]
    return SearchResult(context_id=context.context_id,algorithm="topic_baseline",status="matched",candidates=candidates,
        reason_codes=["topic_tag_jaccard_overlap"],eligible_materials=len(eligible),query_has_vocabulary=True,
        continuation_candidates=list(context.continuation_candidates))
