"""Verify and combine separately checkpointed public E5 vector segments."""
import argparse,json,os,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.data_preparation.history_io import file_hash
from app.data_preparation.retrieval_bundle import load_index


def verify_segment_identity(first, second, rows):
    shared=('index_bundle_id','model','revision','model_files_sha256','dimensions','pooling','batch_size')
    if any(first[k]!=second[k] for k in shared): raise ValueError('Segment identity mismatch')
    if first['rows']!=rows or second['end']!=rows or second['start']<0 or second['start']>rows:
        raise ValueError('Invalid segment boundaries')


def verify_vectors(array):
    for start in range(0,len(array),512):
        values=np.asarray(array[start:start+512])
        if not np.isfinite(values).all() or not np.allclose(np.linalg.norm(values,axis=1),1,atol=1e-4):
            raise ValueError('Invalid vector values or norm')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--first-pid',type=int,required=True); args=parser.parse_args()
    pid_path=Path('/proc')/str(args.first_pid)/'cmdline'
    if pid_path.exists() and b'scripts/build_e5_vectors.py' in pid_path.read_bytes():
        raise RuntimeError('First worker is still running')
    index,index_manifest=load_index(ROOT/'artifacts/retrieval')
    first_root=ROOT/'artifacts/e5-vectors'; second_root=ROOT/'artifacts/e5-segment2'
    checkpoint=json.loads((first_root/'checkpoint.json').read_text(encoding='utf-8'))
    segment=json.loads((second_root/'manifest.json').read_text(encoding='utf-8'))
    first,second=checkpoint['identity'],segment['identity']
    verify_segment_identity(first,second,len(index.rows))
    if first['index_bundle_id']!=index_manifest['bundle_id'] or checkpoint['completed_rows']!=second['start']:
        raise ValueError('Incomplete or incompatible first segment')
    right_path=second_root/'vectors.npy'
    if file_hash(right_path)!=segment['vectors_sha256']:raise ValueError('Second segment checksum mismatch')
    left=np.load(first_root/'vectors.partial.npy',mmap_mode='r',allow_pickle=False)
    right=np.load(right_path,mmap_mode='r',allow_pickle=False)
    split=second['start']
    if left.shape!=(len(index.rows),768) or right.shape!=(len(index.rows)-split,768) or left.dtype!=np.float32 or right.dtype!=np.float32:
        raise ValueError('Segment shape or dtype mismatch')
    verify_vectors(left[:split]); verify_vectors(right)
    validation=json.loads((first_root/'prefix_validation_v2.json').read_text(encoding='utf-8'))
    if (validation['checkpoint_sha256']!=file_hash(first_root/'checkpoint.json')
            or validation['index_bundle_id']!=index_manifest['bundle_id']
            or validation['rows_verified']!=np.linspace(0,split-1,num=min(32,split),dtype=int).tolist()
            or validation['matrix_sha256']!=file_hash(first_root/'vectors.partial.npy') or validation['max_abs_difference']>1e-5):
        raise ValueError('Prefix validation mismatch')
    final=first_root/'vectors.npy'; tmp=first_root/'vectors.joining.npy'; report=first_root/'manifest.json'
    if final.exists() or tmp.exists() or report.exists():raise FileExistsError('Output exists; do not overwrite')
    out=np.lib.format.open_memmap(tmp,mode='w+',dtype=np.float32,shape=left.shape)
    for start in range(0,split,512):out[start:min(split,start+512)]=left[start:min(split,start+512)]
    for start in range(0,len(right),512):out[split+start:split+min(len(right),start+512)]=right[start:min(len(right),start+512)]
    out.flush(); del out
    digest=file_hash(tmp)
    os.replace(tmp,final)
    details={'identity':first,'vectors_sha256':digest,'segments':[
        {'start':0,'end':split,'source':'first checkpoint; runtime metadata not recorded at original start; 32 evenly spaced prefix vectors recomputed'},
        {'start':split,'end':len(index.rows),'source_sha256':segment['vectors_sha256'],
         'runtime_versions':second['runtime_versions'],'encoder_code_sha256':second['encoder_code_sha256']}]}
    temp=report.with_suffix('.json.tmp');temp.write_text(json.dumps(details,indent=2),encoding='utf-8');os.replace(temp,report)
    print(json.dumps({'rows':len(index.rows),'split':split,'vectors_sha256':digest},indent=2))
if __name__=='__main__':main()