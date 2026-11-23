"""Small general-purpose ONNX embeddings; not biomedical-specialized."""
from functools import lru_cache
from pathlib import Path
import os
import threading

_lock = threading.Lock()


@lru_cache(maxsize=1)
def runtime():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    directory = Path(os.getenv('MEDSCOUT_EMBED_DIR', '/app/embedding-model'))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    session = ort.InferenceSession(str(directory / 'model.onnx'), sess_options=options,
                                  providers=['CPUExecutionProvider'])
    tokenizer = Tokenizer.from_file(str(directory / 'tokenizer.json'))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding()
    return session, tokenizer


def embed(texts):
    import numpy as np
    vectors = []
    with _lock:
        session, tokenizer = runtime()
        for start in range(0, len(texts), 4):
            encoded = tokenizer.encode_batch(texts[start:start + 4])
            inputs = {'input_ids': np.array([x.ids for x in encoded], dtype=np.int64),
                      'attention_mask': np.array([x.attention_mask for x in encoded], dtype=np.int64),
                      'token_type_ids': np.array([x.type_ids for x in encoded], dtype=np.int64)}
            needed = {x.name for x in session.get_inputs()}
            hidden = session.run(None, {k: v for k, v in inputs.items() if k in needed})[0]
            mask = inputs['attention_mask'][..., None]
            pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            vectors.extend(pooled)
    return np.array(vectors)


def rerank(question, citations, top_k=5):
    """Chunk current live retrieval results and cosine-rank excerpts.

    This is an ephemeral vector index over PubMed candidates, not a persistent
    comprehensive medical corpus. Retrieval alone does not establish truth.
    """
    if not citations:
        return []
    chunks = []
    for source in citations:
        text = source['text'][:12000]
        for offset in range(0, len(text), 800):
            excerpt = text[offset:offset + 1000]
            if excerpt:
                chunks.append({**source, 'text': excerpt, 'offset': offset})
    chunks = chunks[:60]
    vectors = embed([question] + [r['metadata']['title'] + '\n' + r['text'] for r in chunks])
    similarities = vectors[1:] @ vectors[0]
    order = similarities.argsort()[::-1][:top_k]
    return [{**chunks[int(i)], 'retrieval_score': float(similarities[i]),
             'embedding_model': 'MiniLM-L6-v2 · general-purpose int8 ONNX'} for i in order]
