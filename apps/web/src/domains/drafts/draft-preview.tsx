export function DraftPreview() {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <p className="eyebrow">Drafts</p>
          <h2>초안 준비 상태</h2>
        </div>
        <button className="ghost-button" type="button">
          템플릿 보기
        </button>
      </div>

      <ul className="stack-list">
        <li>
          <strong>Project A Summary</strong>
          <span>citation blocks ready</span>
        </li>
        <li>
          <strong>Risk Review Memo</strong>
          <span>2 required fields missing</span>
        </li>
        <li>
          <strong>Export Queue</strong>
          <span>docx/pdf worker not wired yet</span>
        </li>
      </ul>
    </section>
  );
}
