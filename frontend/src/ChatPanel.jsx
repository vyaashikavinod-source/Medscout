import { useState } from "react";

export default function ChatPanel({ onAsk, loading, response, error }) {
  const [text, setText] = useState("");
  const [includeAI, setIncludeAI] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    onAsk(text.trim(), includeAI);
  }

  return (
    <div style={styles.card}>
      <form onSubmit={handleSubmit} style={styles.form}>
        <textarea
          style={styles.textarea}
          placeholder="Search a public research topic, e.g. 'exercise and sleep quality systematic review'. Do not enter identifying or private health information."
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
        />
        <label style={{fontSize:13}}><input type="checkbox" checked={includeAI} onChange={e=>setIncludeAI(e.target.checked)} /> Include a cited Gemini research summary (sends question and excerpts to Google)</label>
        <button type="submit" disabled={loading} style={styles.button}>
          {loading ? "Searching PubMed..." : "Search literature"}
        </button>
      </form>

      {error && <div style={styles.error}>Error: {error}</div>}

      {response && (
        <div style={styles.answerBlock}>
          {response.confidence && (
            <div style={styles.confidence}>
              Confidence: <strong>{response.confidence}</strong>
            </div>
          )}
          <div style={styles.answerText}>{response.answer_text}</div>
          <div style={styles.footerDisclaimer}>{response.disclaimer}</div>
        </div>
      )}
    </div>
  );
}

const styles = {
  card: { background: "#fff", border: "1px solid #e2e2e2", borderRadius: 12, padding: 18 },
  form: { display: "flex", flexDirection: "column", gap: 10 },
  textarea: {
    resize: "vertical",
    padding: 10,
    fontSize: 14,
    borderRadius: 8,
    border: "1px solid #ccc",
    fontFamily: "inherit",
  },
  button: {
    alignSelf: "flex-start",
    padding: "8px 18px",
    borderRadius: 8,
    border: "none",
    background: "#1a4d8f",
    color: "#fff",
    fontSize: 14,
    cursor: "pointer",
  },
  error: { marginTop: 12, color: "#a10000", fontSize: 13.5 },
  answerBlock: { marginTop: 18, borderTop: "1px solid #eee", paddingTop: 14 },
  confidence: { fontSize: 13, color: "#555", marginBottom: 8, textTransform: "capitalize" },
  answerText: { whiteSpace: "pre-wrap", lineHeight: 1.55, fontSize: 14.5 },
  footerDisclaimer: { marginTop: 14, fontSize: 12, color: "#888", fontStyle: "italic" },
};
