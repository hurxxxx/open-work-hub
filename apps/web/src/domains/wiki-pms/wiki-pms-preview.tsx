export function WikiPmsPreview() {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Wiki / PMS</p>
          <h2>Preview-first 제안</h2>
        </div>
        <span className="status-badge status-badge--muted">preview only</span>
      </div>

      <ul className="stack-list">
        <li>
          <strong>Issue triage</strong>
          <span>owner reassign preview available</span>
        </li>
        <li>
          <strong>Wiki summary</strong>
          <span>grounded summary with source links</span>
        </li>
      </ul>
    </section>
  );
}
