"""
Layer 2 — Retrieval: vector store.

FAISS chosen over Chroma for the prototype: no server process, single file
persisted to disk, trivial to reason about. Swap in Chroma later if you need
richer metadata filtering without hand-rolling it (see `search` below for
where that filtering currently happens in-process instead).
"""
from __future__ import annotations

import argparse
import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from backend.ingestion.chunking import Chunk, chunk_by_paragraph, chunk_guideline_page, chunk_structured_abstract
from backend.retrieval.embed import embed_texts

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PUBMED_DIR = DATA_DIR / "pubmed"
GUIDELINE_DIR = DATA_DIR / "guidelines"
INDEX_DIR = DATA_DIR / "index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH = INDEX_DIR / "faiss.index"
METADATA_PATH = INDEX_DIR / "chunks.pkl"


@dataclass
class RetrievedChunk:
    text: str
    section: str
    metadata: dict
    score: float

    def to_dict(self) -> dict:
        return {"text": self.text, "section": self.section, "metadata": self.metadata, "score": self.score}


class VectorStore:
    def __init__(self):
        self.index: faiss.Index | None = None
        self.chunks: list[Chunk] = []

    # ---------- build ----------
    def build_from_disk(self) -> None:
        all_chunks: list[Chunk] = []

        for path in PUBMED_DIR.glob("*.jsonl"):
            for line in path.read_text().splitlines():
                record = json.loads(line)
                metadata = {
                    "source": record["source"],
                    "title": record["title"],
                    "journal": record["journal"],
                    "pub_date": record["pub_date"],
                    "study_type": record["study_type"],
                    "pmid": record["pmid"],
                }
                all_chunks.extend(chunk_structured_abstract(record["abstract"], metadata))

        for path in GUIDELINE_DIR.glob("*.jsonl"):
            for line in path.read_text().splitlines():
                record = json.loads(line)
                metadata = {
                    "source": record["source"],
                    "title": record["document_title"],
                    "page_number": record["page_number"],
                }
                all_chunks.extend(chunk_guideline_page(record["text"], metadata))

        if not all_chunks:
            raise RuntimeError(
                "No ingested data found. Run backend.ingestion.pubmed_client and/or "
                "backend.ingestion.guideline_parser first."
            )

        embeddings = embed_texts([c.text for c in all_chunks])
        dim = embeddings.shape[1]

        index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors == cosine sim
        index.add(embeddings)

        self.index = index
        self.chunks = all_chunks
        self._persist()
        print(f"Built index with {len(all_chunks)} chunks (dim={dim}) -> {INDEX_PATH}")

    def _persist(self) -> None:
        faiss.write_index(self.index, str(INDEX_PATH))
        with METADATA_PATH.open("wb") as f:
            pickle.dump(self.chunks, f)

    # ---------- load ----------
    def load(self) -> "VectorStore":
        if not INDEX_PATH.exists() or not METADATA_PATH.exists():
            raise FileNotFoundError(
                f"No index found at {INDEX_PATH}. Run `python -m backend.retrieval.vector_store --build` first."
            )
        self.index = faiss.read_index(str(INDEX_PATH))
        with METADATA_PATH.open("rb") as f:
            self.chunks = pickle.load(f)
        return self

    # ---------- search ----------
    def search(self, query: str, top_k: int = 10, source_filter: list[str] | None = None) -> list[RetrievedChunk]:
        if self.index is None:
            self.load()

        query_vec = embed_texts([query])
        # Over-fetch when filtering by source so we don't starve the reranker.
        fetch_k = top_k * 4 if source_filter else top_k
        scores, indices = self.index.search(query_vec, fetch_k)

        results: list[RetrievedChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            chunk = self.chunks[idx]
            if source_filter and chunk.metadata.get("source") not in source_filter:
                continue
            results.append(RetrievedChunk(text=chunk.text, section=chunk.section, metadata=chunk.metadata, score=float(score)))
            if len(results) >= top_k:
                break
        return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build or query the MedScout vector store.")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--query", default=None)
    args = parser.parse_args()

    store = VectorStore()
    if args.build:
        store.build_from_disk()
    elif args.query:
        store.load()
        for r in store.search(args.query, top_k=5):
            print(f"[{r.score:.3f}] ({r.section}) {r.metadata.get('title')}: {r.text[:160]}...")
