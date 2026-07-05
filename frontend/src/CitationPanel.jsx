export default function CitationPanel({ citations }) {
  return (
    <div style={styles.card}>
      <h3 style={styles.heading}>Citations</h3>
      {citations.length === 0 ? (
        <p style={styles.empty}>No sources retrieved yet — ask a question to see supporting evidence here.</p>
      ) : (
        <ul style={styles.list}>
          {citations.map((c, i) => (
            <li key={i} style={styles.item}>
              <div style={styles.sourceRow}>
                <span style={styles.sourceBadge}>{c.metadata?.source || "unknown"}</span>
                <span style={styles.title}>{c.metadata?.title || "Untitled"}</span>
              </div>
              <p style={styles.excerpt}>&ldquo;{truncate(c.text, 220)}&rdquo;</p>
              <div style={styles.meta}>
                {c.metadata?.study_type && <span>{c.metadata.study_type} · </span>}
                {c.metadata?.pub_date && <span>{c.metadata.pub_date} · </span>}
                {c.section && <span>section: {c.section}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function truncate(text, max) {
  if (!text) return "";
  return text.length > max ? text.slice(0, max).trim() + "..." : text;
}

const styles = {
  card: { background: "#fff", border: "1px solid #e2e2e2", borderRadius: 12, padding: 16 },
  heading: { margin: "0 0 10px", fontSize: 15 },
  empty: { fontSize: 13, color: "#888" },
  list: { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 },
  item: { borderBottom: "1px solid #f0f0f0", paddingBottom: 10 },
  sourceRow: { display: "flex", alignItems: "center", gap: 6, marginBottom: 4 },
  sourceBadge: {
    fontSize: 10.5,
    fontWeight: 700,
    background: "#eef3fb",
    color: "#1a4d8f",
    padding: "2px 6px",
    borderRadius: 4,
    letterSpacing: 0.3,
  },
  title: { fontSize: 12.5, fontWeight: 600, color: "#333" },
  excerpt: { fontSize: 12.5, color: "#444", margin: "4px 0", lineHeight: 1.4 },
  meta: { fontSize: 11, color: "#999" },
};
