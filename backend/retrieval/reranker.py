"""
Layer 2 — Retrieval: cross-encoder reranker.

Bi-encoder retrieval (embed.py + vector_store.py) is fast but scores query
and document independently, so it misses fine-grained interaction between
them. Medical text has a lot of superficially similar but clinically
distinct language ("history of MI" vs "family history of MI" vs "ruling out
MI"), where that interaction is exactly what matters. A cross-encoder scores
(query, document) pairs jointly and is used here purely to re-order an
already-retrieved candidate set — it is too slow to run over the whole
corpus, which is why it sits after the bi-encoder, not instead of it.

Default model: cross-encoder/ms-marco-MiniLM-L-6-v2 (general-domain but
strong and fast). Swap for a biomedical cross-encoder if you find/train one
worth the extra latency — note the swap explicitly in your README either way.
"""
from __future__ import annotations

import os
from functools import lru_cache

from sentence_transformers import CrossEncoder

from backend.retrieval.vector_store import RetrievedChunk

DEFAULT_RERANKER_MODEL = os.environ.get("MEDSCOUT_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


@lru_cache(maxsize=1)
def get_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> CrossEncoder:
    return CrossEncoder(model_name)


def rerank(query: str, candidates: list[RetrievedChunk], top_k: int = 5) -> list[RetrievedChunk]:
    if not candidates:
        return []

    model = get_reranker()
    pairs = [(query, c.text) for c in candidates]
    scores = model.predict(pairs)

    reranked = [
        RetrievedChunk(text=c.text, section=c.section, metadata=c.metadata, score=float(s))
        for c, s in zip(candidates, scores)
    ]
    reranked.sort(key=lambda r: r.score, reverse=True)
    return reranked[:top_k]
