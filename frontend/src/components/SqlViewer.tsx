interface SqlViewerProps {
  title: string;
  sql: string | null;
}

// A syntax-highlighter (e.g. Prism/highlight.js) would be nice-to-have here,
// but for read-only DDL/view-definition display a plain monospace <pre> block
// is perfectly legible and avoids pulling in a fairly heavy dependency (and
// its CSS themes/language grammars) for a single low-traffic view. Revisit if
// this app ever needs to *edit* SQL.
export default function SqlViewer({ title, sql }: SqlViewerProps) {
  if (!sql) {
    return null;
  }

  return (
    <div className="stack">
      <h3>{title}</h3>
      <pre
        style={{
          background: "#0f172a",
          color: "#e2e8f0",
          padding: "0.85rem 1rem",
          borderRadius: 6,
          overflowX: "auto",
          fontSize: "0.82rem",
          lineHeight: 1.5,
          margin: 0,
        }}
      >
        <code>{sql}</code>
      </pre>
    </div>
  );
}
