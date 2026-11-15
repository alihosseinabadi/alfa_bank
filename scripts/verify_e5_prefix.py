"""Recompute a deterministic prefix sample to validate a legacy checkpoint."""
import json,os,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.data_preparation.history_io import file_hash
from app.data_preparation.retrieval_bundle import load_index
from app.ml.e5_retriever import LocalE5Encoder

def main():
    torch.set_num_threads(4)
    index,manifest=load_index(ROOT/'artifacts/retrieval')
    root=ROOT/'artifacts/e5-vectors'; checkpoint_path=root/'checkpoint.json'
    checkpoint=json.loads(checkpoint_path.read_text(encoding='utf-8'))
    done=checkpoint['completed_rows']; identity=checkpoint['identity']
    if done<8 or done%8 or identity['index_bundle_id']!=manifest['bundle_id']:
        raise ValueError('Invalid prefix checkpoint')
    model=ROOT/'artifacts/e5-model'
    for name,digest in identity['model_files_sha256'].items():
        if Path(name).name!=name or file_hash(model/name)!=digest:raise ValueError('Model checksum mismatch')
    vectors=np.load(root/'vectors.partial.npy',mmap_mode='r',allow_pickle=False)
    if vectors.shape!=(len(index.rows),768) or vectors.dtype!=np.float32:raise ValueError('Invalid matrix')
    encoder=LocalE5Encoder(model)
    indices=np.linspace(0,done-1,num=min(32,done),dtype=int).tolist()
    actual=encoder.encode([index.rows[i].text for i in indices],'passage',batch_size=8)
    expected=np.asarray(vectors[indices])
    if not np.allclose(actual,expected,atol=1e-5,rtol=1e-5):raise ValueError('Prefix sample mismatch')
    result={'checkpoint_sha256':file_hash(checkpoint_path),'index_bundle_id':manifest['bundle_id'],
            'rows_verified':indices,'matrix_sha256':file_hash(root/'vectors.partial.npy'),'max_abs_difference':float(np.max(np.abs(actual-expected))),
            'method':'32 evenly spaced public rows recomputed with pinned model; not a full reconstruction'}
    out=root/'prefix_validation_v2.json'
    if out.exists():raise FileExistsError('Existing prefix validation must not be overwritten')
    tmp=out.with_suffix('.json.tmp');tmp.write_text(json.dumps(result,indent=2),encoding='utf-8');os.replace(tmp,out)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()