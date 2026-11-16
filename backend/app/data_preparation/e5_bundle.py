"""Load only validated completed local E5 vectors; never unpickle data."""
import json
from pathlib import Path
import numpy as np
from app.data_preparation.history_io import file_hash
from app.ml.e5_retriever import E5Retriever

EXPECTED_MODEL = "intfloat/multilingual-e5-base"
EXPECTED_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
EXPECTED_WEIGHTS_SHA256 = "a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7"
REQUIRED_MODEL_FILES = {"model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"}


def load_e5_vectors(index, index_manifest, encoder, vector_dir):
    root = Path(vector_dir)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    identity = manifest['identity']
    files = identity['model_files_sha256']
    if (identity['model'] != EXPECTED_MODEL or identity['revision'] != EXPECTED_REVISION
            or set(files) != REQUIRED_MODEL_FILES or files['model.safetensors'] != EXPECTED_WEIGHTS_SHA256):
        raise ValueError('Incompatible E5 model identity')
    if identity['index_bundle_id'] != index_manifest['bundle_id']:
        raise ValueError('E5/index bundle mismatch')
    if identity['rows'] != len(index.rows) or identity['dimensions'] != 768 or identity['pooling'] != 'masked_mean_l2_v1':
        raise ValueError('Incompatible E5 vector contract')
    for name, expected in identity['model_files_sha256'].items():
        if Path(name).name != name or file_hash(Path(encoder.model_dir) / name) != expected:
            raise ValueError('E5 model checksum mismatch')
    path = root / 'vectors.npy'
    if file_hash(path) != manifest['vectors_sha256']:
        raise ValueError('E5 vector checksum mismatch')
    vectors = np.load(path, mmap_mode='r', allow_pickle=False)
    if vectors.shape != (len(index.rows), 768) or vectors.dtype != np.float32 or not np.isfinite(vectors).all():
        raise ValueError('Invalid E5 vector payload')
    if len(vectors) and not np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-4):
        raise ValueError('E5 vectors must be unit length')
    result = E5Retriever(encoder)
    result.materials, result.rows, result.vectors = index.materials, index.rows, vectors
    return result, manifest