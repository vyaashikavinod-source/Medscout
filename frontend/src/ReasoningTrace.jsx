const STEP_LABELS = {
  rule_check: "Deterministic safety check",
  tool_call: "Tool call",
  tool_result: "Tool result",
  llm_text: "Model output",
  model_summary: "AI summary and validation",
  tool_error: "Tool unavailable",
  safety_gate: "Safety gate",
};

const STEP_COLORS = {
  rule_check: "#7f1d1d",
  tool_call: "#1a4d8f",
  tool_result: "#2f6f4f",
  llm_text: "#555",
};

export default function ReasoningTrace({ trace }) {
  return (
    <div style={styles.card}>
      <h3 style={styles.heading}>Reasoning trace</h3>
      {trace.length === 0 ? (
        <p style={styles.empty}>The tool calls, retrieval results and summary-validation status appear here. This is an execution trace, not hidden model reasoning.</p>
      ) : (
        <ol style={styles.list}>
          {trace.map((step, i) => (
            <li key={i} style={styles.item}>
              <span style={{ ...styles.badge, color: STEP_COLORS[step.step_type] || "#333" }}>
                {STEP_LABELS[step.step_type] || step.step_type}
              </span>
              <StepDetail step={step} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function StepDetail({ step }) {
  const { step_type, detail } = step;

  if (step_type === "rule_check") {
    return (
      <div style={styles.detail}>
        {detail.triggered ? (
          <span>Triggered: {detail.matched_rules.map((r) => r.description).join(", ")}</span>
        ) : (
          <span>No red-flag pattern matched.</span>
        )}
      </div>
    );
  }

  if (step_type === "tool_call") {
    return (
      <div style={styles.detail}>
        <code style={styles.code}>{detail.tool}({JSON.stringify(detail.input)})</code>
      </div>
    );
  }

  if (step_type === "tool_result") {
    return (
      <div style={styles.detail}>
        <span>{summarizeResult(detail.tool, detail.result ?? detail)}</span>
      </div>
    );
  }

  if (step_type === "llm_text") {
    return <div style={styles.detail}>{truncate(detail.text, 160)}</div>;
  }

  if (step_type === "model_summary") {
    return <div style={styles.detail}>
      <strong>{detail.status.replaceAll("_", " ")}</strong>
      {detail.model && <span> · {detail.model}</span>}
      {detail.duration_seconds != null && <span> · {detail.duration_seconds.toFixed(2)} s</span>}
      {detail.input_tokens != null && <p>{detail.input_tokens} input / {detail.output_tokens} output tokens</p>}
      {detail.validation && <p>{detail.validation}</p>}
      {detail.failure_stage && <p>{detail.failure_stage.replaceAll("_", " ")}{detail.http_status ? ` · HTTP ${detail.http_status}` : ""}. Source retrieval remains available.</p>}
      {detail.note && <p>{detail.note}</p>}
    </div>;
  }
  if (step_type === "tool_error" || step_type === "safety_gate") {
    return <div style={styles.detail}>{detail.tool || "Safety check"}: {detail.status || "retrieval and synthesis skipped"}</div>;
  }
  return null;
}

function summarizeResult(tool, result) {
  if (Array.isArray(result)) return `Returned ${result.length} result(s)`;
  if (result && typeof result === "object") {
    if ("excerpts" in result) return `${tool}: ranked ${result.excerpts} excerpts with ${result.model}`;
    if ("records" in result) return `${tool}: ${result.records} retrieved excerpts`;
    if ("triggered" in result) return result.triggered ? "Red flag confirmed" : "No red flag";
    if ("n_distinct_sources" in result) return `Found ${result.n_distinct_sources} distinct source(s)`;
    return `Returned data from ${tool}`;
  }
  return String(result);
}

function truncate(text, max) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max).trim() + "..." : text;
}

const styles = {
  card: { background: "#fff", border: "1px solid #e2e2e2", borderRadius: 12, padding: 16 },
  heading: { margin: "0 0 10px", fontSize: 15 },
  empty: { fontSize: 13, color: "#888" },
  list: { margin: 0, padding: "0 0 0 18px", display: "flex", flexDirection: "column", gap: 10 },
  item: { fontSize: 12.5 },
  badge: { fontWeight: 700, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.3 },
  detail: { marginTop: 2, color: "#333", lineHeight: 1.4 },
  code: { fontFamily: "monospace", fontSize: 11.5, background: "#f5f5f5", padding: "2px 5px", borderRadius: 4 },
};
