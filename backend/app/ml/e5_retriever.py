"""Local E5 embeddings over the same public eligible rows as TF-IDF."""
import numpy as np
from .profile_contracts import CONTEXT_VERSION
from .tfidf_retriever import prepare_corpus, eligible_for_context


class LocalE5Encoder:
    """Mean-pool the last layer with padding masked, then L2-normalize."""
    def __init__(self, model_dir, device="cpu"):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.model_dir = model_dir
        self.torch = torch
        self.device = torch.device(device)
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        self.model = AutoModel.from_pretrained(str(model_dir), local_files_only=True).to(self.device).eval()

    def encode(self, texts, kind, batch_size=8):
        if kind not in ("query", "passage") or batch_size < 1:
            raise ValueError("Invalid E5 input kind or batch size")
        batches = []
        for start in range(0, len(texts), batch_size):
            encoded = self.tokenizer([kind + ": " + t for t in texts[start:start + batch_size]],
                                     padding=True, truncation=True, max_length=512, return_tensors="pt")
            encoded = {key: value.to(self.device) for key, value in encoded.items()}
            with self.torch.inference_mode():
                hidden = self.model(**encoded).last_hidden_state
                mask = encoded["attention_mask"].unsqueeze(-1)
                vectors = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                vectors = self.torch.nn.functional.normalize(vectors, p=2, dim=1)
            batches.append(vectors.cpu().numpy().astype(np.float32))
        return np.concatenate(batches) if batches else np.empty((0, self.model.config.hidden_size), dtype=np.float32)


class E5Retriever:
    def __init__(self, encoder):
        self.encoder = encoder
        self.materials, self.rows = {}, []
        self.vectors = None

    def fit(self, materials, chunks, batch_size=8):
        self.materials, self.rows = prepare_corpus(materials, chunks)
        self.vectors = self.encoder.encode([r.text for r in self.rows], "passage", batch_size=batch_size)
        if self.vectors.ndim != 2 or len(self.vectors) != len(self.rows) or not np.isfinite(self.vectors).all():
            raise ValueError("Invalid embedding matrix")
        return self

    def query(self, context, k=50):
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if self.vectors is None:
            raise ValueError("Index has not been fitted")
        if not context.query_text.strip() or not self.rows:
            return []
        query = self.encoder.encode([context.query_text], "query")
        if query.shape != (1, self.vectors.shape[1]) or not np.isfinite(query).all():
            raise ValueError("Invalid query vector")
        scores = self.vectors @ query[0]
        best = {}
        for i, row in enumerate(self.rows):
            if not eligible_for_context(self.materials[row.material_key], context):
                continue
            score = float(scores[i])
            previous = best.get(row.material_key)
            if previous is None or score > previous[0] or (score == previous[0] and row.chunk_id < previous[1].chunk_id):
                best[row.material_key] = (score, row)
        return [(key, score, row) for key, (score, row) in sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:min(k, 50)]]