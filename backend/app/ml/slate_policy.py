"""Sequential epsilon-greedy slate over an already eligible UCB ranking."""
import math
import random
from .ranking_contracts import SlateRankedMaterial, SlateRankingResult, UCBRankingResult, RankingReason
from .feature_registry import REGISTRY_HASH, validate_features

POLICY = 'epsilon-diverse-slate-v1'

def select_slate(ucb, *, seed, epsilon=0.1, diversity_weight=0.05, relevance_gap=0.15, k=6, topics_by_key=None, topic_weight=0.05):
    if not isinstance(ucb, UCBRankingResult) or ucb.feature_registry_hash != REGISTRY_HASH or not ucb.model_state_id:
        raise ValueError('incompatible UCB ranking')
    if not isinstance(seed, int) or not 0 <= seed < 2**63 or not isinstance(k, int) or not 0 <= k <= 6:
        raise ValueError('invalid seed or slate size')
    if not math.isfinite(epsilon) or not 0 < epsilon <= 1 or not math.isfinite(diversity_weight) or not 0 <= diversity_weight <= 1:
        raise ValueError('invalid policy parameters')
    if not math.isfinite(relevance_gap) or not 0 <= relevance_gap <= 1: raise ValueError('invalid relevance guard')
    pool = list(ucb.candidates)
    if len(pool) > 50 or len({c.material_key for c in pool}) != len(pool): raise ValueError('duplicate or oversized pool')
    for card in pool:
        validate_features(card.features)
        if not math.isfinite(card.ucb_score) or not math.isfinite(card.exploit) or not math.isfinite(card.explore) or card.explore < 0 or not math.isclose(card.ucb_score,card.exploit+card.explore,rel_tol=1e-10,abs_tol=1e-12): raise ValueError('invalid UCB scores')
    if topics_by_key is not None:
        if set(topics_by_key) != {c.material_key for c in pool}: raise ValueError('topic snapshot mismatch')
        topic_penalties([c.material_key for c in pool], topics_by_key, [], topic_weight)
    rng = random.Random(seed)
    if any(not math.isfinite(c.prior_score) for c in pool): raise ValueError('invalid prior score')
    threshold = max((c.prior_score for c in pool), default=0) - relevance_gap
    available = [c for c in pool if c.prior_score >= threshold]
    chosen, counts, selected_keys = [], {}, []
    exploratory_slot = min(k, len(available)) - 1
    while available and len(chosen) < k:
        topics = topic_penalties([c.material_key for c in available],topics_by_key,selected_keys,topic_weight) if topics_by_key is not None else {}
        penalties = [diversity_weight * counts.get(c.item_type,0) + topics.get(c.material_key,0) for c in available]
        best = min(range(len(available)), key=lambda i: (-(available[i].ucb_score-penalties[i]),available[i].retrieval_rank,available[i].material_key))
        active_epsilon = epsilon if len(chosen) == exploratory_slot else 0.0
        base = active_epsilon / len(available)
        probabilities = [base + (1-active_epsilon if i==best else 0.0) for i in range(len(available))]
        draw, cumulative, selected = rng.random(), 0.0, len(available)-1
        for idx, probability in enumerate(probabilities):
            cumulative += probability
            if draw < cumulative:
                selected = idx; break
        card = available.pop(selected)
        data = card.model_dump()
        data.update(rank=len(chosen)+1,selection_probability=probabilities[selected],diversity_penalty=penalties[selected])
        if topics_by_key is not None and penalties[selected] > 0:
            reason = RankingReason(feature="diversity_penalty", value=penalties[selected], source="public_catalog_topics_and_format", text="Оценка снижена за повтор формата или темы среди уже выбранных материалов.")
            data["reasons"] = list(data["reasons"]) + [reason.model_dump()]
        chosen.append(SlateRankedMaterial.model_validate(data))
        counts[card.item_type] = counts.get(card.item_type,0)+1
        selected_keys.append(card.material_key)
    data = ucb.model_dump(exclude={'candidates'})
    version = 'epsilon-diverse-slate-v2' if topics_by_key is not None else POLICY
    data.update(version=version, policy_id=version, candidates=chosen, eligible_candidates=pool,
                seed=seed,epsilon=epsilon,diversity_weight=diversity_weight,relevance_gap=relevance_gap,requested_k=k, topics_by_key=topics_by_key, topic_weight=topic_weight if topics_by_key is not None else 0.0)
    return SlateRankingResult.model_validate(data)

def replay_slate(result):
    data = result.model_dump(exclude={'eligible_candidates','seed','epsilon','diversity_weight','requested_k','relevance_gap','topics_by_key','topic_weight','candidates'})
    data.update(version='shared-linucb-ranking-v1',candidates=result.eligible_candidates)
    base = UCBRankingResult.model_validate(data)
    return select_slate(base,seed=result.seed,epsilon=result.epsilon,diversity_weight=result.diversity_weight,relevance_gap=result.relevance_gap,k=result.requested_k,topics_by_key=result.topics_by_key,topic_weight=result.topic_weight)

def replay_record(record):
    """Reconstruct choices and propensities using only persisted policy fields."""
    pool=record['pool']; gap=record['relevance_gap']; eps=record['epsilon']; weight=record['diversity_weight']
    if len({p['material_key'] for p in pool}) != len(pool): raise ValueError('duplicate pool')
    threshold=max((p['prior_score'] for p in pool),default=0)-gap
    available=[p for p in pool if p['prior_score']>=threshold]
    rng=random.Random(record['seed']); counts={}; out=[]; selected_keys=[]
    slot=min(record['requested_k'],len(available))-1
    while available and len(out)<record['requested_k']:
        topics = topic_penalties([c['material_key'] for c in available],record['topics_by_key'],selected_keys,record['topic_weight']) if record.get('topics_by_key') is not None else {}
        penalties=[weight*counts.get(c['item_type'],0)+topics.get(c['material_key'],0) for c in available]
        best=min(range(len(available)),key=lambda i:(-(available[i]['ucb_score']-penalties[i]),available[i]['retrieval_rank'],available[i]['material_key']))
        e=eps if len(out)==slot else 0.0
        probs=[e/len(available)+(1-e if i==best else 0) for i in range(len(available))]
        x=rng.random(); total=0.; index=len(available)-1
        for i,p in enumerate(probs):
            total+=p
            if x<total: index=i; break
        card=available.pop(index)
        out.append((card['material_key'],probs[index]))
        counts[card['item_type']]=counts.get(card['item_type'],0)+1
        selected_keys.append(card['material_key'])
    return out

def topic_penalties(material_keys, topics_by_key, selected_keys, weight):
    """Return an auditable soft penalty based only on supplied public catalog topics.

    This helper does not change v1 slate decisions or historical propensity.
    Caller must obtain topics from the pinned catalog, not from a user request.
    """
    import math
    if not math.isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError('invalid topic diversity weight')
    if len(set(material_keys)) != len(material_keys):
        raise ValueError('duplicate material')
    if any(k not in topics_by_key for k in material_keys + selected_keys):
        raise ValueError('topic snapshot missing material')
    def labels(k):
        values = topics_by_key[k]
        if not isinstance(values, list) or any(not isinstance(v,str) or not v.strip() for v in values):
            raise ValueError('invalid catalog topics')
        return {v.strip().casefold().replace('ё','е') for v in values}
    seen = set().union(*(labels(k) for k in selected_keys)) if selected_keys else set()
    return {k: weight * len(labels(k) & seen) / len(labels(k)) if labels(k) else 0.0 for k in material_keys}
