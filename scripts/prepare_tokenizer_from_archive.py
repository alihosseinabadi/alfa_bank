"""Extract only a checksum-verified pinned tokenizer from supplied E5 archives."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.data_preparation.contracts import ENCODER, ENCODER_REVISION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-zip', type=Path, required=True)
    parser.add_argument('--vectors-zip', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/e5-tokenizer')
    args = parser.parse_args()
    with ZipFile(args.model_zip) as model, ZipFile(args.vectors_zip) as vectors:
        identity = json.loads(vectors.read('e5-vectors/manifest.json'))['identity']
        if identity['model'] != ENCODER or identity['revision'] != ENCODER_REVISION:
            raise ValueError('E5 tokenizer revision is incompatible')
        member = model.getinfo('e5-model/tokenizer.json')
        if member.file_size > 64 * 1024 * 1024:
            raise ValueError('Tokenizer archive entry is unexpectedly large')
        tokenizer = model.read(member)
        digest = hashlib.sha256(tokenizer).hexdigest()
        if digest != identity['model_files_sha256']['tokenizer.json']:
            raise ValueError('Tokenizer checksum mismatch')
    manifest = {'model': ENCODER, 'revision': ENCODER_REVISION, 'files': {'tokenizer.json': digest}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out, metadata = args.output_dir / 'tokenizer.json', args.output_dir / 'catalog_tokenizer.json'
    if out.exists() or metadata.exists():
        if not out.is_file() or not metadata.is_file() or hashlib.sha256(out.read_bytes()).hexdigest() != digest or json.loads(metadata.read_text(encoding='utf-8')) != manifest:
            raise ValueError('Existing tokenizer differs; refusing to overwrite')
        print('Existing verified tokenizer reused')
        return
    out.write_bytes(tokenizer)
    metadata.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Pinned tokenizer extracted and verified; no model weights extracted')


if __name__ == '__main__':
    main()
