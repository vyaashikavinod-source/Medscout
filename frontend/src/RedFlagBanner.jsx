// Same visual-urgency pattern as a "SUSPICIOUS/ATTACK" badge in a detection
// dashboard: impossible to miss, color-coded, and rendered from the
// deterministic rule layer's output — not from anything the LLM said.
export default function RedFlagBanner({ redFlag }) {
  if (!redFlag?.triggered) return null;

  return (
    <div style={styles.banner} role="alert">
      <div style={styles.iconAndTitle}>
        <span style={styles.icon}>&#9888;</span>
        <span style={styles.title}>Seek immediate care if this applies to you</span>
      </div>
      <ul style={styles.list}>
        {redFlag.matched_rules.map((rule) => (
          <li key={rule.id} style={styles.item}>
            <strong>{rule.description}.</strong> {rule.guidance}
          </li>
        ))}
      </ul>
      <p style={styles.note}>
        This determination came from a deterministic safety rule check, not the AI's
        judgment, and cannot be overridden by the rest of this tool's response.
      </p>
    </div>
  );
}

const styles = {
  banner: {
    background: "#fdecea",
    border: "2px solid #d32f2f",
    borderRadius: 10,
    padding: "14px 18px",
    marginBottom: 20,
  },
  iconAndTitle: { display: "flex", alignItems: "center", gap: 8, marginBottom: 8 },
  icon: { fontSize: 20, color: "#d32f2f" },
  title: { fontSize: 16, fontWeight: 700, color: "#7f1d1d" },
  list: { margin: "0 0 8px", paddingLeft: 20 },
  item: { fontSize: 13.5, color: "#5c1414", marginBottom: 4, lineHeight: 1.4 },
  note: { fontSize: 11.5, color: "#8a3a3a", margin: 0, fontStyle: "italic" },
};
