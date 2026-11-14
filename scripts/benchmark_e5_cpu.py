"""Measure local E5 inference on a small public catalog sample."""
import json, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.data_preparation.retrieval_bundle import load_index
from app.ml.e5_retriever import LocalE5Encoder
import torch

def main():
    torch.set_num_threads(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
    index, _ = load_index(ROOT/'artifacts/retrieval')
    start = time.perf_counter()
    encoder = LocalE5Encoder(ROOT/'artifacts/e5-model')
    loaded = time.perf_counter()
    vectors = encoder.encode([r.text for r in index.rows[:32]], 'passage', 8)
    end = time.perf_counter()
    print(json.dumps({'samples':len(vectors),'dimensions':vectors.shape[1], 'load_seconds':loaded-start,'encode_seconds':end-loaded,'device':'cpu'}))
if __name__=='__main__': main()