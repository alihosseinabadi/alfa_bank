"""Trusted stage-9 orchestration over already filtered prior candidates."""
from app.ml.ucb_ranking import rank_with_fallback
from sqlalchemy.exc import OperationalError, DisconnectionError

def issue_recommendations(event_service, actor, request_key, prior, context, retrieval_batch,
                          model_loader, *, k=6, simulated=False, epsilon=.1,
                          diversity_weight=.05, relevance_gap=.15, catalog_materials=None, topic_weight=.05):
    if not isinstance(k,int) or isinstance(k,bool) or not 1 <= k <= 6:
        raise ValueError('k must be an integer between 1 and 6')
    try:
        ranked, failure = rank_with_fallback(prior, model_loader)
    except (OperationalError,DisconnectionError):
        ranked, failure = prior, 'database_unavailable'
    if failure is not None:
        # Original prior positions are already consecutive; do not publish 50 on fallback.
        limited = prior.model_copy(update={'candidates': prior.candidates[:k]}, deep=True)
        issued = event_service.issue(actor,request_key,limited,context,retrieval_batch=retrieval_batch,simulated=simulated)
        return {'decision':issued,'result':limited.candidates,'fallback_reason':failure}
    topics = None
    if catalog_materials is not None:
        owners = {m.material_key:m for m in catalog_materials}
        if len(owners) != len(catalog_materials) or any(c.material_key not in owners for c in ranked.candidates):
            raise ValueError('catalog does not match candidates')
        topics = {c.material_key:list(owners[c.material_key].topics) for c in ranked.candidates}
    issued, selected = event_service.issue_randomized(actor,request_key,ranked,context,retrieval_batch=retrieval_batch,
        simulated=simulated,epsilon=epsilon,diversity_weight=diversity_weight,relevance_gap=relevance_gap,k=k,return_selected=True,topics_by_key=topics,topic_weight=topic_weight)
    return {'decision':issued,'result':selected,'fallback_reason':None}
