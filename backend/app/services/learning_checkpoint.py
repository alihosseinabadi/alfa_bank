"""Checksummed, atomic JSON checkpoint; ledger replay remains authoritative."""
import hashlib, json, os, tempfile
import numpy as np
from app.ml.linucb import SharedLinUCB

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def write_checkpoint(path, service):
    model = service.replay()
    body = {'format':'linucb-checkpoint-v1', 'identity':service.identity, 'state_id':model.state_id,
            'ridge':model.ridge, 'alpha':model.alpha, 'dimension':model.dimension,
            'A':model.A.tolist(), 'b':model.b.tolist()}
    envelope = {'body':body, 'sha256':hashlib.sha256(canonical(body)).hexdigest()}
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix='.linucb-', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(canonical(envelope)); output.flush(); os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return model.state_id

def load_checkpoint(path, service):
    with open(path, 'rb') as source: envelope = json.load(source)
    body = envelope['body']
    if hashlib.sha256(canonical(body)).hexdigest() != envelope['sha256'] or body['format'] != 'linucb-checkpoint-v1' or body['identity'] != service.identity:
        raise ValueError('invalid or incompatible checkpoint')
    checkpoint = SharedLinUCB(body['dimension'], body['ridge'], body['alpha'], body['A'], body['b'])
    current = service.replay()
    if checkpoint.state_digest() != current.state_digest() or body['state_id'] != current.state_id or not np.array_equal(checkpoint.A,current.A) or not np.array_equal(checkpoint.b,current.b):
        raise ValueError('checkpoint does not match current ledger')
    checkpoint.state_id = current.state_id
    checkpoint.matrix_digest = current.matrix_digest
    return checkpoint
