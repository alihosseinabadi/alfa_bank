import pytest
from collections import Counter
from uuid import uuid4, UUID
from app.ml.prior_ranking import rank_candidates
from app.ml.linucb import SharedLinUCB
from app.ml.feature_registry import FEATURE_DIMENSION
from app.ml.ucb_ranking import rank_ucb
from app.ml.slate_policy import select_slate, replay_slate
from app.services.event_service import EventConflict
from app.models.events import Decision, DecisionItem
from test_event_storage_stage7 import store, actor
from test_prior_ranking_stage6 import setup, material

def make_slate(seed=4,k=2,epsilon=.3):
    mats=[material('a',item_type='article'),material('b',item_type='webinar'),material('c',item_type='article')]
    p, ctx, mats, batch = setup(materials=mats)
    prior = rank_candidates(batch,mats,ctx,profile=p,k=50)
    model = SharedLinUCB(FEATURE_DIMENSION)
    model.state_id='synthetic'; model.matrix_digest=model.state_digest()
    ucb = rank_ucb(prior,model,model.state_id)
    return select_slate(ucb,seed=seed,k=k,epsilon=epsilon,relevance_gap=1.0),ucb,ctx,batch

def test_replay_unique_probability_and_invalid():
    slate, ucb, _, _=make_slate()
    assert replay_slate(slate)==slate
    assert len({c.material_key for c in slate.candidates})==2
    assert all(0 < c.selection_probability <= 1 for c in slate.candidates)
    assert len(select_slate(ucb,seed=0,k=6,relevance_gap=1.0).candidates)==3
    assert len(select_slate(ucb,seed=0,k=0).candidates)==0
    with pytest.raises(ValueError): select_slate(ucb,seed=0,epsilon=0)

def test_empirical_first_slot_probabilities():
    slate, ucb, _, _=make_slate(epsilon=.3)
    counts=Counter(select_slate(ucb,seed=n,k=1,epsilon=.3,relevance_gap=1.0).candidates[0].material_key for n in range(700))
    best=ucb.candidates[0].material_key
    assert counts[best]/700 == pytest.approx(.8,abs=.055)
    assert sum(counts.values())==700

def test_issue_slate_records_conditional_and_rejects_tampering(store):
    service,sessions,_=store
    result,ucb,ctx,batch=make_slate()
    who=actor(); key=uuid4()
    issued=service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,epsilon=.3,k=2,relevance_gap=1.0)
    assert service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,epsilon=.3,k=2,relevance_gap=1.0)['replayed']
    with sessions() as db:
        decision=db.get(Decision,UUID(issued['decision_id']))
        assert decision.snapshot['selection_mode']=='epsilon_diverse'
        assert decision.snapshot['action_probability'] is None
        assert len(decision.snapshot['metadata']['slate']['pool'])==3
        item=db.get(DecisionItem,UUID(issued['items'][0]['item_id']))
        assert 0 < item.snapshot['slate']['conditional_probability'] <= 1
    bad=result.model_copy(deep=True)
    bad.candidates[0].selection_probability=1.0
    with pytest.raises(EventConflict): service.issue(who,uuid4(),bad,ctx,retrieval_batch=batch)

def test_ips_support_and_effective_sample_size():
    from app.ml.offpolicy_stage9 import ips
    row={'behavior':{'a':.5,'b':.5},'target':{'a':1.,'b':0.},'chosen':'a','reward':1.}
    out=ips([row,dict(row,chosen='b',reward=0.)])
    assert out['ips']==1 and out['effective_sample_size']==1 and out['max_weight']==2
    with pytest.raises(ValueError,match='support'): ips([dict(row,behavior={'a':0.,'b':1.})])
    with pytest.raises(ValueError): ips([dict(row,behavior={'a':.9,'b':.5})])

def test_one_exploratory_slot_and_cap():
    result,ucb,_,_=make_slate(k=3)
    assert all(c.selection_probability == 1.0 for c in result.candidates[:-1])
    assert result.candidates[-1].selection_probability > 0
    with pytest.raises(ValueError): select_slate(ucb,seed=1,k=7)

def test_reconstruct_from_database_and_next_step_validation(store):
    from app.ml.slate_policy import replay_record
    service,sessions,_=store
    _,ucb,ctx,batch=make_slate()
    who=actor(); key=uuid4()
    issued=service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,epsilon=.3,k=2,relevance_gap=1.0)
    with sessions() as db:
        decision=db.get(Decision,UUID(issued['decision_id']))
        logged=decision.snapshot['metadata']['slate']
        actual=[]
        for item in issued['items']:
            row=db.get(DecisionItem,UUID(item['item_id']))
            actual.append((row.material_key,row.snapshot['slate']['conditional_probability']))
        assert replay_record(logged)==actual
    modified=ucb.model_copy(deep=True)
    modified.candidates[0].next_step.url='https://different.invalid/'
    with pytest.raises(EventConflict):
        service.issue_randomized(who,uuid4(),modified,ctx,retrieval_batch=batch,epsilon=.3,k=2,relevance_gap=1.0)

def test_logged_replay_matches_policy_across_random_seeds():
    from app.ml.slate_policy import replay_record
    _,ucb,_,_=make_slate()
    for seed in range(100):
        result=select_slate(ucb,seed=seed,k=3,epsilon=.3,relevance_gap=1.0)
        record={'pool':[{'material_key':c.material_key,'item_type':c.item_type,'retrieval_rank':c.retrieval_rank,'ucb_score':c.ucb_score,'prior_score':c.prior_score} for c in result.eligible_candidates], 'seed':seed,'epsilon':.3,'diversity_weight':result.diversity_weight,'relevance_gap':1.0,'requested_k':3}
        assert replay_record(record)==[(c.material_key,c.selection_probability) for c in result.candidates]

def test_reserved_seed_prevents_changing_inputs(store):
    service,_,_=store
    _,ucb,ctx,batch=make_slate()
    who=actor(); key=uuid4()
    service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,k=2,relevance_gap=1.0)
    with pytest.raises(EventConflict):
        service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,k=3,relevance_gap=1.0)

def test_orchestrator_failure_limits_prior_and_logs_prior(store):
    from app.services.recommendation_orchestrator import issue_recommendations
    service,sessions,_=store
    p,ctx,mats,batch=setup(materials=[material('a'),material('b'),material('c')])
    prior=rank_candidates(batch,mats,ctx,profile=p,k=50)
    def fail(): raise OSError('unavailable')
    result=issue_recommendations(service,actor(),uuid4(),prior,ctx,batch,fail,k=2)
    assert result['fallback_reason']=='OSError'
    assert len(result['result'])==2
    assert len(result['decision']['items'])==2
    with sessions() as db:
        decision=db.get(Decision,UUID(result['decision']['decision_id']))
        assert decision.snapshot['selection_mode']=='deterministic'

def test_orchestrator_returns_selected_cards_without_seed(store):
    from app.services.recommendation_orchestrator import issue_recommendations
    service,_,_=store
    p,ctx,mats,batch=setup(materials=[material('a'),material('b'),material('c')])
    prior=rank_candidates(batch,mats,ctx,profile=p,k=50)
    model=SharedLinUCB(FEATURE_DIMENSION); model.state_id='test'; model.matrix_digest=model.state_digest()
    result=issue_recommendations(service,actor(),uuid4(),prior,ctx,batch,lambda:model,k=2,relevance_gap=1.0)
    assert result['fallback_reason'] is None
    assert [c.material_key for c in result['result']] == [i['material_key'] for i in result['decision']['items']]
    assert len(result['result'])==2

def test_topic_diversity_uses_public_labels_and_handles_unknown():
    from app.ml.slate_policy import topic_penalties
    topics={'a':['Налоги'], 'b':['налоги','Финансы'], 'c':['Управление'], 'd':[]}
    assert topic_penalties(['b','c','d'],topics,['a'],.2)=={'b':.1,'c':0.,'d':0.}
    with pytest.raises(ValueError): topic_penalties(['missing'],topics,['a'],.2)

def test_topic_v2_replay_and_old_v1_unchanged(store):
    from app.ml.slate_policy import replay_record
    service,sessions,_=store
    _,ucb,ctx,batch=make_slate()
    topics={c.material_key: (['Налоги'] if c.material_key in ('a','b') else ['Маркетинг']) for c in ucb.candidates}
    old=select_slate(ucb,seed=2,k=3,relevance_gap=1.0)
    result=select_slate(ucb,seed=2,k=3,relevance_gap=1.0,topics_by_key=topics,topic_weight=.2)
    assert old.version=='epsilon-diverse-slate-v1'
    assert result.version=='epsilon-diverse-slate-v2'
    assert replay_slate(result)==result
    who=actor(); key=uuid4()
    issued=service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,k=3,relevance_gap=1.0,topics_by_key=topics,topic_weight=.2)
    with sessions() as db:
        decision=db.get(Decision,UUID(issued['decision_id']))
        log=decision.snapshot['metadata']['slate']
        actual=[(x['material_key'],db.get(DecisionItem,UUID(x['item_id'])).snapshot['slate']['conditional_probability']) for x in issued['items']]
        assert replay_record(log)==actual
        assert log['topics_by_key']==topics
    assert service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,k=3,relevance_gap=1.0,topics_by_key=topics,topic_weight=.2)['replayed']
    with pytest.raises(EventConflict):
        service.issue_randomized(who,key,ucb,ctx,retrieval_batch=batch,k=3,relevance_gap=1.0,topics_by_key=topics,topic_weight=.3)

def test_orchestrator_v2_uses_catalog_topics(store):
    from app.services.recommendation_orchestrator import issue_recommendations
    service,sessions,_=store
    p,ctx,mats,batch=setup(materials=[material('a'),material('b'),material('c')])
    prior=rank_candidates(batch,mats,ctx,profile=p,k=50)
    model=SharedLinUCB(FEATURE_DIMENSION); model.state_id='test'; model.matrix_digest=model.state_digest()
    result=issue_recommendations(service,actor(),uuid4(),prior,ctx,batch,lambda:model,k=2,relevance_gap=1.0,catalog_materials=mats)
    with sessions() as db:
        decision=db.get(Decision,UUID(result['decision']['decision_id']))
        assert decision.snapshot['metadata']['version']=='epsilon-diverse-slate-v2'

def test_topic_penalty_changes_order_without_affecting_v1():
    _,ucb,_,_=make_slate()
    pool=ucb.model_copy(deep=True)
    for c in pool.candidates:
        c.exploit=1.0; c.explore=0.; c.ucb_score=1.0; c.prior_score=1.0
    # Equal scores and equal formats isolate the public-topic penalty.
    for c in pool.candidates: c.item_type='article'
    topics={'a':['Налоги'],'b':['Налоги'],'c':['Маркетинг']}
    v1=select_slate(pool,seed=7,k=3,epsilon=.01,relevance_gap=1,diversity_weight=0)
    v2=select_slate(pool,seed=7,k=3,epsilon=.01,relevance_gap=1,diversity_weight=0,topics_by_key=topics,topic_weight=.5)
    assert [c.material_key for c in v1.candidates[:2]]==['a','b']
    assert [c.material_key for c in v2.candidates[:2]]==['a','c']
    assert v2.candidates[1].selection_probability==1.0

def test_v2_explains_nonzero_diversity_penalty():
    _,ucb,_,_=make_slate()
    topics={c.material_key:['Тема'] for c in ucb.candidates}
    result=select_slate(ucb,seed=3,k=3,relevance_gap=1,topics_by_key=topics,topic_weight=.2)
    for card in result.candidates:
        reasons=[r for r in card.reasons if r.feature=='diversity_penalty']
        assert bool(reasons)==(card.diversity_penalty>0)
        if reasons: assert reasons[0].value==card.diversity_penalty
    assert replay_slate(result)==result

def test_slate_rejects_fabricated_public_excerpt(store):
    service,_,_=store
    _,ucb,ctx,batch=make_slate()
    corrupted=ucb.model_copy(deep=True)
    corrupted.candidates[0].citations[0].excerpt='Несуществующее утверждение'
    with pytest.raises(EventConflict, match='excerpt'):
        service.issue_randomized(actor(),uuid4(),corrupted,ctx,retrieval_batch=batch,k=2,relevance_gap=1.0)
