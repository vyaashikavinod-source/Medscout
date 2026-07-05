"""
Layer 3 — Reasoning & Safety: orchestrator.

Hand-rolled function-calling loop against the Anthropic API rather than a
framework like LangGraph — for a system this size, a plain loop makes the
control flow (and where the safety override sits inside it) easy to read
and easy to audit, which matters more here than the extra abstraction would
buy us.

THE ONE RULE THIS FILE ENFORCES: `check_red_flags` runs before anything else,
outside of the LLM's control, and its result is layered onto the final
response regardless of what the LLM says. The LLM is never given the chance
to reason the red-flag result away — it's composed in after the LLM turn,
not passed back in as a tool result the model could argue with.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import anthropic

from backend.agent.red_flag_rules import check_red_flags
from backend.agent.tools import TOOL_DEFINITIONS, TOOL_IMPLEMENTATIONS

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
MODEL = os.environ.get("MEDSCOUT_LLM_MODEL", "claude-sonnet-4-6")
MAX_AGENT_TURNS = 6

SYSTEM_PROMPT = """You are MedScout, a research/education assistant that reasons over \
retrieved public medical literature (PubMed abstracts, CDC/WHO/NIH guidance) to help \
answer symptom-related questions.

Hard rules, non-negotiable:
1. You are NOT a diagnostic tool and must never claim to diagnose. Frame findings as \
"possible considerations" grounded in retrieved evidence, never as a diagnosis.
2. Reason ONLY over content returned by your tools in this conversation. Never state a \
clinical claim from unconstrained memory — if you haven't retrieved it, say you don't \
have evidence for it rather than filling the gap.
3. Always call search_literature (and compare_sources/summarize_consensus when the \
question involves potentially conflicting evidence) before making any evidence claim.
4. Every claim you make must be attributable to a specific retrieved chunk. Structure \
your final answer as: possible considerations, supporting evidence with source \
attribution, an explicit confidence level (low/moderate/high) based on source \
agreement and study type, and any caveats.
5. A deterministic safety check has already run outside of your control. If you are \
told it was triggered, do not minimize, second-guess, or argue against it — incorporate \
it as the most urgent part of your response.
6. This is a research/education prototype using public literature. It does not replace \
professional medical advice. Reinforce this when relevant, especially for anything \
serious."""


@dataclass
class ReasoningStep:
    step_type: str            # "rule_check" | "tool_call" | "tool_result" | "llm_text"
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"step_type": self.step_type, "detail": self.detail}


@dataclass
class MedScoutResponse:
    red_flag: dict
    answer_text: str
    citations: list[dict]
    confidence: str | None
    reasoning_trace: list[dict]

    def to_dict(self) -> dict:
        return {
            "red_flag": self.red_flag,
            "answer_text": self.answer_text,
            "citations": self.citations,
            "confidence": self.confidence,
            "reasoning_trace": self.reasoning_trace,
        }


def run_query(user_question: str, client: anthropic.Anthropic | None = None) -> MedScoutResponse:
    trace: list[ReasoningStep] = []

    # --- Step 0: deterministic safety layer, OUTSIDE the LLM's control ----
    red_flag_result = check_red_flags(user_question)
    trace.append(ReasoningStep("rule_check", red_flag_result.to_dict()))
    if LLM_PROVIDER == "mock" or not os.getenv("ANTHROPIC_API_KEY"):
        citations = TOOL_IMPLEMENTATIONS["search_literature"](query=user_question)

        top_points = []
        for c in citations[:3]:
           text = c.get("text", "").strip()
           title = c.get("metadata", {}).get("title", "retrieved source")
           if text:
                top_points.append(f"- {text[:350]}... ({title})")

        answer = (
            "MedScout is running in retrieval-only mode, so this response is a literature-grounded summary "
            "rather than an LLM-generated clinical explanation.\n\n"
            "Possible considerations from retrieved evidence:\n"
            + "\n".join(top_points)
            + "\n\nThis is not a diagnosis and does not replace professional medical advice."
       )
        if red_flag_result.triggered:
            answer = (
                "Red-flag symptoms may be present. Please seek urgent medical care or call your local emergency number. "
                + answer
            )

        trace.append(ReasoningStep("tool_call", {
            "tool": "search_literature",
            "input": {"query": user_question}
        }))
        trace.append(ReasoningStep("tool_result", {
            "tool": "search_literature",
            "result": _truncate_for_trace(citations)
        }))

        return MedScoutResponse(
            red_flag=red_flag_result.to_dict(),
            answer_text=answer,
            citations=citations,
            confidence="retrieval-only",
            reasoning_trace=[s.to_dict() for s in trace],
        )

    client = client or anthropic.Anthropic()

    messages: list[dict] = [{"role": "user", "content": user_question}]

    # Tell the model the rule-layer's result as an immutable fact, not as
    # something it retrieved and could weigh against other evidence.
    system_prompt = SYSTEM_PROMPT
    if red_flag_result.triggered:
        rules_text = "; ".join(r["description"] for r in red_flag_result.matched_rules)
        system_prompt += (
            f"\n\nSAFETY NOTICE (already determined, not up for debate): the deterministic "
            f"red-flag layer was triggered for this input ({rules_text}). Your response MUST "
            f"lead with this and MUST NOT downplay it, regardless of what the literature says."
        )

    all_citations: list[dict] = []
    final_text = ""

    for _ in range(MAX_AGENT_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b.text for b in response.content if b.type == "text"]
        if text_blocks:
            final_text = "\n".join(text_blocks)
            trace.append(ReasoningStep("llm_text", {"text": final_text}))

        if not tool_use_blocks:
            break  # model is done reasoning, produced its final answer

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in tool_use_blocks:
            trace.append(ReasoningStep("tool_call", {"tool": block.name, "input": block.input}))

            impl = TOOL_IMPLEMENTATIONS.get(block.name)
            if impl is None:
                result: Any = {"error": f"Unknown tool {block.name}"}
            else:
                result = impl(**block.input)

            if block.name == "search_literature" and isinstance(result, list):
                all_citations.extend(result)
            elif block.name in ("compare_sources", "summarize_consensus") and isinstance(result, dict):
                for chunks in result.get("evidence_by_source", result.get("sources", {})).values():
                    all_citations.extend(chunks)

            trace.append(ReasoningStep("tool_result", {"tool": block.name, "result": _truncate_for_trace(result)}))

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result)[:8000],
                }
            )

        messages.append({"role": "user", "content": tool_results})

    confidence = _extract_confidence(final_text)

    # Deduplicate citations by (pmid or title+page)
    seen = set()
    deduped_citations = []
    for c in all_citations:
        key = c.get("metadata", {}).get("pmid") or (
            c.get("metadata", {}).get("title"),
            c.get("metadata", {}).get("page_number"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped_citations.append(c)

    return MedScoutResponse(
        red_flag=red_flag_result.to_dict(),
        answer_text=final_text,
        citations=deduped_citations,
        confidence=confidence,
        reasoning_trace=[s.to_dict() for s in trace],
    )


def _extract_confidence(text: str) -> str | None:
    lowered = text.lower()
    for level in ("high confidence", "moderate confidence", "low confidence"):
        if level in lowered:
            return level.split()[0]
    return None


def _truncate_for_trace(result: Any, max_items: int = 3) -> Any:
    """Keep the reasoning trace readable — full tool payloads are already
    available via citations; the trace just needs to show what happened."""
    if isinstance(result, list):
        return result[:max_items]
    if isinstance(result, dict) and "sources" in result:
        return {k: v[:max_items] for k, v in list(result["sources"].items())[:max_items]}
    if isinstance(result, dict) and "evidence_by_source" in result:
        return {
            "topic": result.get("topic"),
            "n_distinct_sources": result.get("n_distinct_sources"),
        }
    return result
