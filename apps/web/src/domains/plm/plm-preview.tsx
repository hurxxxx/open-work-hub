export function PlmPreview() {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">PLM</p>
          <h2>읽기 전용 조회</h2>
        </div>
        <span className="status-badge">safe preview</span>
      </div>

      <div className="table-shell">
        <div className="table-shell__row table-shell__row--header">
          <span>Item</span>
          <span>Status</span>
          <span>Owner</span>
        </div>
        <div className="table-shell__row">
          <span>BOM-214</span>
          <span>Open</span>
          <span>Kim</span>
        </div>
        <div className="table-shell__row">
          <span>ECO-991</span>
          <span>Delayed</span>
          <span>Lee</span>
        </div>
      </div>
    </section>
  );
}
