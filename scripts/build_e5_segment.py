"""Build a separately checkpointed E5 segment for later integrity-checked merge."""
import argparse, importlib.metadata, json, os, sys, time
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.data_preparation.retrieval_bundle import load_index
from app.data_preparation.history_io import file_hash
from app.ml.e5_retriever import LocalE5Encoder

def write_state(path,data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2),encoding='utf-8')
    os.replace(tmp,path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start',required=True,type=int)
    args=parser.parse_args()
    torch.set_num_threads(4)
    index, manifest=load_index(ROOT/'artifacts/retrieval')
    start=args.start
    if start<0 or start>=len(index.rows) or start%8: raise ValueError('Start must be an aligned valid row')
    output=ROOT/'artifacts/e5-segment2'; output.mkdir(parents=True,exist_ok=True)
    model=ROOT/'artifacts/e5-model'; names=('model.safetensors','config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json')
    identity={'index_bundle_id':manifest['bundle_id'],'model':'intfloat/multilingual-e5-base',
              'revision':'d128750597153bb5987e10b1c3493a34e5a4502a',
              'model_files_sha256':{name:file_hash(model/name) for name in names},
              'start':start,'end':len(index.rows),'dimensions':768,'pooling':'masked_mean_l2_v1','batch_size':8,
              'encoder_code_sha256':file_hash(ROOT/'backend/app/ml/e5_retriever.py'),
              'runtime_versions':{name:importlib.metadata.version(name) for name in ('torch','transformers','tokenizers','numpy')}}
    if identity['model_files_sha256']['model.safetensors'] != 'a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7': raise ValueError('Wrong weights')
    state=output/'checkpoint.json'; partial=output/'vectors.partial.npy'; final=output/'vectors.npy'
    if final.exists(): raise FileExistsError('Completed segment exists')
    if state.exists():
        prev=json.loads(state.read_text(encoding='utf-8'))
        if prev['identity']!=identity: raise ValueError('Segment checkpoint differs')
        done=prev['completed_rows']; arr=np.load(partial,mmap_mode='r+',allow_pickle=False)
        if arr.shape!=(len(index.rows)-start,768) or arr.dtype!=np.float32: raise ValueError('Bad segment shape')
    else:
        if partial.exists():raise FileExistsError('Unrecognized segment')
        done=0; arr=np.lib.format.open_memmap(partial,mode='w+',dtype=np.float32,shape=(len(index.rows)-start,768))
        write_state(state,{'identity':identity,'completed_rows':done})
    if not isinstance(done,int) or done<0 or done>len(index.rows)-start:raise ValueError('Bad checkpoint')
    encoder=LocalE5Encoder(model); clock=time.perf_counter()
    while start+done<len(index.rows):
        end=min(done+8,len(index.rows)-start)
        vectors=encoder.encode([r.text for r in index.rows[start+done:start+end]],'passage',batch_size=8)
        if vectors.shape!=(end-done,768) or not np.isfinite(vectors).all():raise ValueError('Bad model output')
        arr[done:end]=vectors; arr.flush(); done=end
        write_state(state,{'identity':identity,'completed_rows':done})
        if done%80==0 or start+done==len(index.rows): print(json.dumps({'segment_done':done,'segment_total':len(index.rows)-start,'seconds':round(time.perf_counter()-clock,1)}),flush=True)
    del arr
    digest=file_hash(partial); os.replace(partial,final)
    write_state(output/'manifest.json',{'identity':identity,'vectors_sha256':digest})
    print(json.dumps({'segment_done':done,'sha256':digest}),flush=True)
if __name__=='__main__':main()