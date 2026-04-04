import { SearchWorkbench } from '../domains/documents/search-workbench';
import { DraftPreview } from '../domains/drafts/draft-preview';
import { PlmPreview } from '../domains/plm/plm-preview';
import { WikiPmsPreview } from '../domains/wiki-pms/wiki-pms-preview';

export function App() {
  return (
    <div className="portal-shell">
      <aside className="portal-sidebar">
        <div className="sidebar-brand">
          <p className="sidebar-brand__eyebrow">Doowon</p>
          <strong>AI Portal</strong>
        </div>

        <nav aria-label="Primary" className="sidebar-nav">
          <div className="sidebar-nav__group">
            <p className="sidebar-nav__label">Workspace</p>
            <button className="sidebar-nav__item sidebar-nav__item--active" type="button">
              Documents
            </button>
            <button className="sidebar-nav__item" type="button">
              PLM
            </button>
            <button className="sidebar-nav__item" type="button">
              Drafts
            </button>
            <button className="sidebar-nav__item" type="button">
              Wiki / PMS
            </button>
          </div>

          <div className="sidebar-nav__group">
            <p className="sidebar-nav__label">Saved Views</p>
            <button className="sidebar-nav__item" type="button">
              Latest specs
            </button>
            <button className="sidebar-nav__item" type="button">
              Export queue
            </button>
            <button className="sidebar-nav__item" type="button">
              Open issues
            </button>
          </div>
        </nav>

        <div className="sidebar-footer">
          <span className="status-badge status-badge--sidebar">Engineering</span>
          <span className="status-badge status-badge--sidebar">RBAC preview</span>
        </div>
      </aside>

      <main className="portal-main">
        <header className="topbar">
          <div>
            <p className="eyebrow">Operations workspace</p>
            <h1>근거형 검색과 작업면 중심의 AI 업무 포털</h1>
            <p className="topbar__description">
              문서 검색, PLM 조회, 초안 준비, 협업 작업면을 하나의 앱 셸 안에서
              이어가는 초기 스캐폴드입니다.
            </p>
          </div>
          <div className="topbar__meta">
            <span className="status-badge">React 19 + Vite</span>
            <span className="status-badge">Nx workspace</span>
            <span className="status-badge">left sidebar</span>
          </div>
        </header>

        <section className="workbench">
          <div className="workbench__main">
            <SearchWorkbench />
          </div>
          <div className="workbench__side">
            <PlmPreview />
            <DraftPreview />
            <WikiPmsPreview />
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
