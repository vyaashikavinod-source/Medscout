import { useState } from "react";
import ChatPanel from "./ChatPanel";
import CitationPanel from "./CitationPanel";
import RedFlagBanner from "./RedFlagBanner";
import ReasoningTrace from "./ReasoningTrace";

const API_BASE = import.meta.env.VITE_MEDSCOUT_API_BASE || "http://localhost:8000";

export default function App() {
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function askQuestion(question) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const data = await res.json();
      setResponse(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>MedScout</h1>
        <p style={styles.subtitle}>Clinical Research &amp; Triage Reasoning Agent</p>
      </header>

      {/* Disclaimer lives in the UI itself, not just the README — always visible. */}
      <div style={styles.disclaimer}>
        <strong>Research/education prototype using public literature.</strong> Not a
        diagnostic tool. Does not replace professional medical advice. If this is an
        emergency, call your local emergency number now.
      </div>

      {response?.red_flag?.triggered && <RedFlagBanner redFlag={response.red_flag} />}

      <div style={styles.body}>
        <div style={styles.mainColumn}>
          <ChatPanel onAsk={askQuestion} loading={loading} response={response} error={error} />
        </div>
        <div style={styles.sideColumn}>
          <CitationPanel citations={response?.citations || []} />
          <ReasoningTrace trace={response?.reasoning_trace || []} />
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    maxWidth: 1100,
    margin: "0 auto",
    padding: "24px 20px 60px",
    color: "#1a1a1a",
  },
  header: { marginBottom: 8 },
  title: { fontSize: 28, margin: 0 },
  subtitle: { margin: "4px 0 16px", color: "#555" },
  disclaimer: {
    background: "#fff8e1",
    border: "1px solid #f0c14b",
    borderRadius: 8,
    padding: "10px 14px",
    fontSize: 13.5,
    color: "#5a4400",
    marginBottom: 20,
  },
  body: {
    display: "grid",
    gridTemplateColumns: "1.4fr 1fr",
    gap: 20,
    alignItems: "start",
  },
  mainColumn: { minWidth: 0 },
  sideColumn: { display: "flex", flexDirection: "column", gap: 16, minWidth: 0 },
};
