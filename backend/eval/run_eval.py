"""
The eval story. Same ablation instinct as rules-only vs rules+statistical vs
rules+statistical+ML in a fraud detector, just for this domain:

  1. red_flag_only          — precision/recall on the red-flag test set
  2. retrieval_only         — does plain vector search surface an on-topic source?
  3. retrieval_plus_reranker— does the reranker measurably improve that?
  4. full_agent             — rules + retrieval + reranker + LLM synthesis,
                               with false-negative rate on red-flags reported
                               separately because it matters more than overall
                               accuracy in a safety context.

NOTE on retrieval metrics: this harness does not (yet) have gold
document-level relevance judgments — building those is the natural next
step once you have a fixed corpus. In the meantime, retrieval_only and
retrieval_plus_reranker use a topical-overlap proxy (does the top-ranked
chunk's text meaningfully overlap with the case's labeled `topic`?) as a
stand-in. Swap `_is_topically_relevant` for a real gold-label lookup once
you've hand-labeled top results for your corpus — the rest of the harness
doesn't need to change.

Usage:
    python -m backend.eval.run_eval [--skip-agent]
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from backend.agent.red_flag_rules import check_red_flags
from backend.retrieval.reranker import rerank
from backend.retrieval.vector_store import VectorStore

EVAL_DIR = Path(__file__).resolve().parent
TEST_CASES_PATH = EVAL_DIR / "test_cases.json"
RESULTS_PATH = EVAL_DIR / "results.json"

_STOPWORDS = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "is", "are", "with"}


def _keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 3}


def _is_topically_relevant(chunk_text: str, topic: str) -> bool:
    chunk_kw = _keywords(chunk_text)
    topic_kw = _keywords(topic)
    if not topic_kw:
        return False
    overlap = chunk_kw & topic_kw
    return len(overlap) / len(topic_kw) >= 0.3


@dataclass
class LayerMetrics:
    layer: str
    precision: float | None
    recall: float | None
    f1: float | None
    red_flag_false_negative_rate: float | None
    n_cases: int

    def to_dict(self) -> dict:
        return asdict(self)


def _prf1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def load_cases() -> list[dict]:
    return json.loads(TEST_CASES_PATH.read_text())


def eval_red_flag_only(cases: list[dict]) -> LayerMetrics:
    tp = fp = fn = tn = 0
    for case in cases:
        predicted = check_red_flags(case["symptom_text"]).triggered
        actual = case["should_trigger_red_flag"]
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    precision, recall, f1 = _prf1(tp, fp, fn)
    fn_rate = fn / (tp + fn) if (tp + fn) else 0.0
    return LayerMetrics("red_flag_only", precision, recall, f1, fn_rate, len(cases))


def eval_retrieval(cases: list[dict], use_reranker: bool) -> LayerMetrics:
    store = VectorStore().load()
    tp = fn = 0

    for case in cases:
        topic = case["topic"]
        candidates = store.search(topic, top_k=15)
        if use_reranker:
            top = rerank(topic, candidates, top_k=3)
        else:
            top = candidates[:3]

        hit = any(_is_topically_relevant(c.text, topic) for c in top)
        if hit:
            tp += 1
        else:
            fn += 1

    precision = tp / len(cases) if cases else 0.0
    recall = precision  # single-relevant-hit proxy: precision@k and recall@k coincide here
    f1 = precision
    layer_name = "retrieval_plus_reranker" if use_reranker else "retrieval_only"
    return LayerMetrics(layer_name, precision, recall, f1, None, len(cases))


def eval_full_agent(cases: list[dict]) -> LayerMetrics:
    """Runs the whole orchestrator, including the LLM call. Requires
    ANTHROPIC_API_KEY and a built vector index. This re-checks the red-flag
    false-negative rate through the composite path as a regression guard —
    it should match eval_red_flag_only exactly, since the rule layer is
    deterministic and untouched by the LLM. If it doesn't match, that's a
    bug in the orchestrator's override wiring, not the rule layer."""
    from backend.agent.orchestrator import run_query  # deferred: needs API key at import-adjacent call time

    tp = fp = fn = 0
    for case in cases:
        result = run_query(case["symptom_text"])
        predicted = result.red_flag["triggered"]
        actual = case["should_trigger_red_flag"]
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1

    precision, recall, f1 = _prf1(tp, fp, fn)
    fn_rate = fn / (tp + fn) if (tp + fn) else 0.0
    return LayerMetrics("full_agent", precision, recall, f1, fn_rate, len(cases))


def main(skip_agent: bool = False) -> None:
    cases = load_cases()
    results = [eval_red_flag_only(cases)]

    try:
        results.append(eval_retrieval(cases, use_reranker=False))
        results.append(eval_retrieval(cases, use_reranker=True))
    except FileNotFoundError as e:
        print(f"[skip] retrieval evals: {e}")

    if not skip_agent:
        try:
            results.append(eval_full_agent(cases))
        except Exception as e:  # noqa: BLE001 — surface any failure (missing key, index, etc.) without crashing the whole run
            print(f"[skip] full_agent eval: {e}")

    RESULTS_PATH.write_text(json.dumps([r.to_dict() for r in results], indent=2))

    header = f"{'Layer':<28}{'Precision':<12}{'Recall':<10}{'F1':<8}{'Red-flag FN rate':<18}"
    print(header)
    print("-" * len(header))
    for r in results:
        fn_rate = f"{r.red_flag_false_negative_rate:.2f}" if r.red_flag_false_negative_rate is not None else "—"
        print(f"{r.layer:<28}{r.precision:<12.2f}{r.recall:<10.2f}{r.f1:<8.2f}{fn_rate:<18}")

    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-agent", action="store_true", help="Skip the full_agent eval (no API key needed).")
    args = parser.parse_args()
    main(skip_agent=args.skip_agent)
