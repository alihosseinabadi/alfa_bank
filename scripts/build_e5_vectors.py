"""Build a resumable local E5 matrix for the verified public retrieval index."""
import hashlib, importlib.metadata, json, os, sys, time
from pathlib import Path
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.data_preparation.retrieval_bundle import load_index
from app.data_preparation.history_io import file_hash
from app.ml.e5_retriever import LocalE5Encoder


def save_json_atomic(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def main():
    torch.set_num_threads(4)
    idx, manifest = load_index(ROOT / 'artifacts/retrieval')
    model = ROOT / 'artifacts/e5-model'
    output = ROOT / 'artifacts/e5-vectors'
    output.mkdir(parents=True, exist_ok=True)
    model_files = ('model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json')
    identity = {'index_bundle_id': manifest['bundle_id'], 'model': 'intfloat/multilingual-e5-base',
                'revision': 'd128750597153bb5987e10b1c3493a34e5a4502a',
                'model_files_sha256': {name: file_hash(model/name) for name in model_files},
                'rows': len(idx.rows), 'dimensions': 768, 'pooling': 'masked_mean_l2_v1', 'batch_size': 8,
                'encoder_code_sha256': file_hash(ROOT / 'backend/app/ml/e5_retriever.py'),
                'runtime_versions': {name: importlib.metadata.version(name) for name in ('torch','transformers','tokenizers','numpy')}}
    if identity['model_files_sha256']['model.safetensors'] != 'a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7':
        raise ValueError('Unexpected E5 model weights')
    state_path = output / 'checkpoint.json'
    partial_path = output / 'vectors.partial.npy'
    final_path = output / 'vectors.npy'
    if final_path.exists():
        raise FileExistsError('Completed or unverified output exists; do not overwrite it')
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state['identity'] != identity or not partial_path.exists():
            raise ValueError('Existing checkpoint is incompatible or incomplete')
        vectors = np.load(partial_path, mmap_mode='r+', allow_pickle=False)
        if vectors.shape != (len(idx.rows), 768) or vectors.dtype != np.float32:
            raise ValueError('Existing vector matrix has invalid shape or dtype')
        done = state['completed_rows']
        if not isinstance(done, int) or done < 0 or done > len(idx.rows):
            raise ValueError('Invalid checkpoint row count')
    else:
        if partial_path.exists(): raise FileExistsError('Unrecognized partial vector file')
        vectors = np.lib.format.open_memmap(partial_path, mode='w+', dtype=np.float32, shape=(len(idx.rows), 768))
        done = 0
        save_json_atomic(state_path, {'identity': identity, 'completed_rows': done})
    encoder = LocalE5Encoder(model)
    start = time.perf_counter()
    while done < len(idx.rows):
        end = min(done + 8, len(idx.rows))
        batch = encoder.encode([row.text for row in idx.rows[done:end]], 'passage', batch_size=8)
        if batch.shape != (end-done, 768) or not np.isfinite(batch).all():
            raise ValueError('Invalid model output')
        vectors[done:end] = batch
        vectors.flush()
        done = end
        save_json_atomic(state_path, {'identity': identity, 'completed_rows': done})
        if done % 80 == 0 or done == len(idx.rows):
            print(json.dumps({'done': done, 'total': len(idx.rows), 'elapsed_seconds': round(time.perf_counter()-start, 1)}), flush=True)
    del vectors
    digest = file_hash(partial_path)
    os.replace(partial_path, final_path)
    save_json_atomic(output/'manifest.json', {'identity': identity, 'vectors_sha256': digest})
    print(json.dumps({'done':done, 'vectors_sha256':digest}), flush=True)
if __name__ == '__main__': main()