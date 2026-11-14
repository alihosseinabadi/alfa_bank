"""Experimental local hybrid search; threshold requires validation on dev only."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.data_preparation.retrieval_bundle import load_index
from app.data_preparation.e5_bundle import load_e5_vectors
from app.ml.e5_retriever import LocalE5Encoder
from app.ml.bm25_retriever import BM25Retriever
from app.ml.hybrid_retriever import HybridRetriever
from app.ml.tfidf_retriever import tokenize_text
from app.ml.evidence import lexical_excerpt
from search_materials import context_for_case
import torch

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--task',default='')
    p.add_argument('--formats',nargs='*',default=[],choices=['course','article','document','webinar','podcast','glossary','calculator'])
    p.add_argument('--free-only',action='store_true')
    p.add_argument('--time-minutes',type=int)
    p.add_argument('--semantic-threshold',type=float,required=True)
    p.add_argument('--k',type=int,default=6)
    args=p.parse_args(); torch.set_num_threads(4)
    index, manifest=load_index(ROOT/'artifacts/retrieval')
    model=LocalE5Encoder(ROOT/'artifacts/e5-model')
    semantic, _=load_e5_vectors(index,manifest,model,ROOT/'artifacts/e5-vectors')
    lexical=BM25Retriever().fit(list(index.materials.values()),index.rows)
    ctx=context_for_case({'task':args.task,'formats':args.formats,'available_time_minutes':args.time_minutes,
                          'budget_preference':'free_only' if args.free_only else None})
    rows=HybridRetriever(semantic,lexical,semantic_threshold=args.semantic_threshold).query(ctx,args.k)
    cards=[]
    for key, score, evidence in rows:
        m=index.materials[key]
        channels=sorted(evidence)
        citations={}
        for channel, data in evidence.items():
            chunk=data['chunk']
            excerpt=lexical_excerpt(chunk.text,tokenize_text(ctx.query_text)) if channel=='lexical' else chunk.text[:360]
            citations[channel]={'chunk_id':chunk.chunk_id,'source_ids':chunk.source_block_ids,
                                'excerpt':excerpt, 'channel_score':data['score']}

        reason=('Совпадение по словам и смыслу.' if len(channels)==2 else
                'Совпадение по словам запроса.' if 'lexical' in evidence else 'Совпадение по смыслу запроса.')
        cards.append({'material_key':key,'title':m.title,'format':m.item_type,'url':m.url,
                      'access':m.access_type,'listed_price':m.listed_price,'duration_minutes':m.duration_minutes,
                      'url_state':m.url_state,'reason':reason,'channels':channels,'fusion_score':score,
                      'evidence_by_channel':citations})
    print(json.dumps({'experimental':True,'profile_mode':'synthetic_only','status':'matched' if cards else 'needs_clarification',
                      'clarification':None if cards else 'Уточните задачу или измените ограничения.',
                      'candidates':cards},ensure_ascii=False,indent=2))
if __name__=='__main__':main()