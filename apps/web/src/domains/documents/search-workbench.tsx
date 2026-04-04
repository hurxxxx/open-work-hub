export function SearchWorkbench() {
  return (
    <section className="panel panel--primary">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Documents</p>
          <h2>근거형 검색 워크벤치</h2>
        </div>
        <button className="ghost-button" type="button">
          최근 질의 불러오기
        </button>
      </div>

      <div className="search-bar">
        <input
          aria-label="Global search"
          className="search-bar__input"
          defaultValue="compressor specification latest revision"
          type="search"
        />
        <button className="primary-button" type="button">
          검색
        </button>
      </div>

      <div className="filter-row">
        <span className="filter-chip">Spec</span>
        <span className="filter-chip">Project A</span>
        <span className="filter-chip">Engineering</span>
      </div>

      <div className="results-grid">
        <article className="result-card">
          <div className="result-card__meta">SPEC · 2026-04-02</div>
          <h3>KX-21 Compressor Specification</h3>
          <p>
            Pressure rating, seal material, and revision history are already
            indexed for grounded answers.
          </p>
          <div className="result-card__footer">
            <span>pp. 4-7</span>
            <span>ACL: engineering</span>
          </div>
        </article>
        <article className="result-card">
          <div className="result-card__meta">REVISION NOTE · 2026-03-28</div>
          <h3>Seal Material Change Notice</h3>
          <p>
            Captures the latest material change with page-level citation
            anchors.
          </p>
          <div className="result-card__footer">
            <span>p. 2</span>
            <span>ACL: engineering</span>
          </div>
        </article>
      </div>
    </section>
  );
}
