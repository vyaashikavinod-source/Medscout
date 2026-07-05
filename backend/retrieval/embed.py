"""
Layer 2 — Retrieval: embeddings.

Uses a biomedical-tuned sentence embedding model rather than a generic one.
Generic embedding models routinely conflate clinically distinct phrases
("myocardial infarction" vs "myocarditis") because they weren't trained on
biomedical text — this is a deliberate, callable-out design choice, not an
afterthought.

Default model: pritamdeka/S-PubMedBert-MS-MARCO
  (PubMedBERT backbone, fine-tuned for retrieval/asymmetric search — closer
  to what we need than a base BioBERT checkpoint, which is better suited to
  classification/NER than sentence-level retrieval.)
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = os.environ.get("MEDSCOUT_EMBED_MODEL", "pritamdeka/S-PubMedBert-MS-MARCO")


@lru_cache(maxsize=1)
def get_embedder(model_name: str = DEFAULT_MODEL) -> SentenceTransformer:
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], model_name: str = DEFAULT_MODEL, batch_size: int = 32) -> np.ndarray:
    model = get_embedder(model_name)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,  # so FAISS inner-product == cosine similarity
        convert_to_numpy=True,
    )
    return embeddings.astype("float32")


def embed_query(query: str, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    return embed_texts([query], model_name=model_name)[0]
