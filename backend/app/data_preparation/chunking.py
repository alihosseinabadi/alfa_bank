"""Deterministic paragraph-first chunks, measured with the released E5 tokenizer."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from .contracts import Chunk, ContentBlock, Material, ENCODER_REVISION

def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class E5Tokenizer:
    def __init__(self, directory: Path):
        from tokenizers import Tokenizer
        manifest = json.loads((directory / "catalog_tokenizer.json").read_text())
        if manifest["revision"] != ENCODER_REVISION:
            raise ValueError("Tokenizer revision mismatch")
        expected = manifest["files"]["tokenizer.json"]
        if hashlib.sha256((directory / "tokenizer.json").read_bytes()).hexdigest() != expected:
            raise ValueError("Tokenizer checksum mismatch")
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()

    def count(self, text: str) -> int:
        return len(self.tokenizer.encode(text).ids)

def chunk_blocks(materials: list[Material], blocks: list[ContentBlock], tokenizer, target_tokens: int = 360, max_tokens: int = 512) -> list[Chunk]:
    if not 64 <= target_tokens <= 400 or not target_tokens <= max_tokens <= 512:
        raise ValueError("Invalid chunk token limits")
    owners = {m.material_key: m for m in materials}
    groups = defaultdict(list)
    for block in blocks:
        if block.material_key not in owners:
            raise ValueError("Orphan content block")
        groups[(block.material_key, block.access_scope, block.entitlement_key, block.content_kind)].append(block)
    chunks = []
    counters = defaultdict(int)
    for (key, scope, entitlement, kind), group in sorted(groups.items(), key=lambda x: tuple(str(v) for v in x[0])):
        material = owners[key]
        if not material.is_discoverable:
            continue
        prefix = "passage: " + material.title + "\n\n"
        if tokenizer.count(prefix) >= target_tokens - 8:
            raise ValueError(f"Title too long for chunk budget: {key}")
        pieces = []
        for block in sorted(group, key=lambda b: (b.order, b.block_id)):
            for paragraph in block.text.split("\n\n"):
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                # Character boundaries preserve exact text. Every final fragment
                # is re-encoded; there is no silent tokenizer truncation.
                while tokenizer.count(prefix + paragraph) > target_tokens:
                    lo, hi = 1, len(paragraph)
                    while lo < hi:
                        mid = (lo + hi + 1) // 2
                        if tokenizer.count(prefix + paragraph[:mid]) <= target_tokens:
                            lo = mid
                        else:
                            hi = mid - 1
                    end = paragraph.rfind(" ", 0, lo + 1)
                    if end < lo // 2:
                        end = lo
                    pieces.append((paragraph[:end].strip(), block.block_id))
                    paragraph = paragraph[end:].strip()
                if paragraph:
                    pieces.append((paragraph, block.block_id))
        pending, refs = [], []
        def emit():
            if not pending:
                return
            text = prefix + "\n\n".join(pending)
            count = tokenizer.count(text)
            if count > max_tokens:
                raise ValueError("Chunk exceeded tokenizer limit")
            source_ids = list(dict.fromkeys(refs))
            content_hash = digest({"text": text, "scope": scope, "entitlement": entitlement})
            ordinal = counters[key]
            counters[key] += 1
            chunk_id = digest({"key": key, "order": ordinal, "sources": source_ids, "content": content_hash, "revision": ENCODER_REVISION})
            chunks.append(Chunk(chunk_id=chunk_id, material_key=key, order=ordinal, text=text,
                source_block_ids=source_ids, access_scope=scope, entitlement_key=entitlement,
                token_count=count, content_hash=content_hash))
        for text, ref in pieces:
            if pending and tokenizer.count(prefix + "\n\n".join(pending + [text])) > target_tokens:
                emit()
                pending, refs = [], []
            pending.append(text)
            refs.append(ref)
        emit()
    return chunks
