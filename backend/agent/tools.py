"""
Layer 3 — Reasoning & Safety: agent tools.

Four tools exposed to the LLM via function-calling. Every tool call and its
result gets appended to a reasoning trace so the dashboard can show exactly
what the agent looked at and why (Layer 4's ReasoningTrace panel reads this
directly).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.agent.red_flag_rules import check_red_flags
from backend.retrieval.reranker import rerank
from backend.retrieval.vector_store import RetrievedChunk, VectorStore

_store: VectorStore | None = None


def _get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore().load()
    return _store


# --- tool implementations ---------------------------------------------------

def search_literature(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over the vector store, reranked with the cross-encoder."""
    candidates = _get_store().search(query, top_k=top_k * 3)
    top = rerank(query, candidates, top_k=top_k)
    return [c.to_dict() for c in top]


def check_red_flags_tool(symptoms: str) -> dict:
    """Deterministic safety rule check. Thin wrapper so the agent loop and
    the eval harness call the exact same code path as everything else."""
    return check_red_flags(symptoms).to_dict()


def compare_sources(topic: str, top_k: int = 8) -> dict:
    """Pulls multiple sources on the same topic and groups them so their
    claims can be diffed, rather than returning one flattened list."""
    candidates = _get_store().search(topic, top_k=top_k * 2)
    top = rerank(topic, candidates, top_k=top_k)

    by_source: dict[str, list[dict]] = defaultdict(list)
    for c in top:
        by_source[c.metadata.get("source", "unknown")].append(c.to_dict())

    return {"topic": topic, "sources": dict(by_source)}


def summarize_consensus(topic: str, top_k: int = 8) -> dict:
    """Synthesizes agreement/disagreement across sources. This function
    itself does NOT call the LLM — it hands back the grouped evidence, and
    the orchestrator's LLM call is what actually writes the synthesis, so
    that synthesis stays grounded only in what this tool actually returned."""
    grouped = compare_sources(topic, top_k=top_k)
    n_sources = len(grouped["sources"])
    return {
        "topic": topic,
        "n_distinct_sources": n_sources,
        "evidence_by_source": grouped["sources"],
    }


# --- tool schema for the Anthropic API function-calling interface ----------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_literature",
        "description": "Semantic search over ingested PubMed abstracts and public guideline text. Returns reranked, cited chunks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query, e.g. a clinical question or symptom description"},
                "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_red_flags",
        "description": "Deterministic safety rule check against known emergency symptom combinations. ALWAYS call this first for any symptom-related question. Its result can override the rest of the response.",
        "input_schema": {
            "type": "object",
            "properties": {"symptoms": {"type": "string", "description": "The user's raw symptom description"}},
            "required": ["symptoms"],
        },
    },
    {
        "name": "compare_sources",
        "description": "Pulls multiple sources on the same topic, grouped by source, so their claims can be compared.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "top_k": {"type": "integer", "default": 8},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "summarize_consensus",
        "description": "Gathers evidence across distinct sources on a topic to support a consensus-vs-conflict judgment. Does not itself decide consensus — returns grouped evidence for the caller to reason over.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "top_k": {"type": "integer", "default": 8},
            },
            "required": ["topic"],
        },
    },
]

TOOL_IMPLEMENTATIONS = {
    "search_literature": lambda **kwargs: search_literature(**kwargs),
    "check_red_flags": lambda **kwargs: check_red_flags_tool(**kwargs),
    "compare_sources": lambda **kwargs: compare_sources(**kwargs),
    "summarize_consensus": lambda **kwargs: summarize_consensus(**kwargs),
}
