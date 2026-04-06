import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { AUTH_TOKEN_STORAGE_KEY } from './auth-api';
import App from './app';

function jsonResponse(payload: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(payload), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('App', () => {
  let container: HTMLDivElement;
  let root: Root;

  async function renderApp() {
    flushSync(() => {
      root.render(<App />);
    });
    await settle();
  }

  async function settle() {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  function findElementByText(text: RegExp): HTMLElement | null {
    return (
      Array.from(document.body.querySelectorAll<HTMLElement>('*')).find((element) => {
        const content = element.textContent ?? '';
        if (!text.test(content)) {
          return false;
        }

        return !Array.from(element.children).some((child) =>
          text.test(child.textContent ?? ''),
        );
      }) ?? null
    );
  }

  function clickMatchingElement(
    text: RegExp,
    selector = 'button, [role="button"], tr, article',
  ) {
    const element = findElementByText(text);
    const clickable = element?.closest<HTMLElement>(selector) ?? element;
    clickable?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    window.history.replaceState({}, '', '/');
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    localStorage.clear();
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, 'test-token');
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/bootstrap-status')) {
        return Promise.resolve(jsonResponse({ requires_setup: false }));
      }
      if (url.endsWith('/api/v1/auth/me')) {
        return Promise.resolve(
          jsonResponse({
            id: 'user-1',
            email: 'admin@aidoo.local',
            full_name: 'AIDOO Admin',
            is_admin: true,
          }),
        );
      }
      if (url.endsWith('/api/v1/auth/logout')) {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith('/api/v1/search/documents')) {
        return Promise.resolve(
          jsonResponse({
            scenario_id: 'documents-rag',
            query_profile: 'bm25 + vector + rerank',
            filters_applied: {
              doc_type: ['spec'],
              project: [],
              department: ['Engineering'],
            },
            hits: [
              {
                document_id: 'doc-spec-001',
                title: 'KX-21 Compressor Specification',
                summary: 'Pressure rating and seal material revisions indexed',
                source_type: 'spec',
                score: 0.94,
                updated: '2026-04-02',
                project: 'Project A',
                department: 'Engineering',
                acl: 'engineering',
                owner: 'Engineering Standards Team',
                page_reference: 'pp. 4-7',
                citation:
                  'Revision R12 updates the approved seal material and tightens the pressure rating requirement for high-temperature operation.',
                next_actions: ['Open source document', 'Attach citation blocks to draft'],
              },
              {
                document_id: 'doc-revision-002',
                title: 'Seal Material Change Notice',
                summary: 'Revision note with page-level citation anchors',
                source_type: 'revision-note',
                score: 0.89,
                updated: '2026-03-28',
                project: 'Project A',
                department: 'Engineering',
                acl: 'engineering',
                owner: 'Component Review Board',
                page_reference: 'pp. 2-3',
                citation:
                  'Change notice confirms the seal material replacement and links the update to project-specific approval history.',
                next_actions: ['Review approval chain', 'Compare against current BOM'],
              },
            ],
            next_actions: [
              'Open top-ranked evidence',
              'Attach citation blocks',
              'Switch to grounded answer',
            ],
            grounded_answer: null,
          }),
        );
      }
      if (url.endsWith('/api/v1/pms/dashboard/summary')) {
        return Promise.resolve(
          jsonResponse({
            project_count: 1,
            active_issue_count: 2,
            overdue_issue_count: 1,
            my_issue_count: 1,
            milestone_due_soon_count: 1,
            status_counts: [
              { status: 'backlog', label: 'Backlog', count: 1 },
              { status: 'todo', label: 'Todo', count: 1 },
              { status: 'in_progress', label: 'In Progress', count: 1 },
              { status: 'done', label: 'Done', count: 0 },
              { status: 'canceled', label: 'Canceled', count: 0 },
            ],
            priority_counts: [
              { priority: 'medium', label: 'Medium', count: 1 },
              { priority: 'high', label: 'High', count: 1 },
            ],
            projects: [
              {
                project_id: 'project-1',
                key: 'AID',
                name: 'AIDOO PMS',
                progress: 0.5,
                open_issue_count: 2,
                overdue_issue_count: 1,
                next_due_date: '2026-04-09',
              },
            ],
            recent_activity: [
              {
                id: 'activity-1',
                issue_id: 'issue-1',
                issue_reference: 'AID-1',
                message: 'AIDOO Admin created AID-1.',
                actor_name: 'AIDOO Admin',
                created_at: '2026-04-05T09:00:00',
              },
            ],
          }),
        );
      }
      if (url.includes('/api/v1/pms/projects?page=1&page_size=20')) {
        return Promise.resolve(
          jsonResponse({
            items: [
              {
                id: 'project-1',
                key: 'AID',
                name: 'AIDOO PMS',
                description: 'Lightweight project execution',
                status: 'active',
                archived: false,
                role: 'owner',
                progress: 0.5,
                member_count: 1,
                milestone_count: 1,
                issue_count: 2,
                overdue_issue_count: 1,
                created_at: '2026-04-01T09:00:00',
                updated_at: '2026-04-05T09:00:00',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
        );
      }
      if (url.includes('/api/v1/pms/projects/project-1/members')) {
        return Promise.resolve(
          jsonResponse({
            items: [
              {
                user_id: 'user-1',
                email: 'admin@aidoo.local',
                full_name: 'AIDOO Admin',
                is_admin: true,
                role: 'owner',
                joined_at: '2026-04-01T09:00:00',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
        );
      }
      if (url.includes('/api/v1/pms/projects/project-1/milestones')) {
        return Promise.resolve(
          jsonResponse({
            items: [
              {
                id: 'milestone-1',
                project_id: 'project-1',
                title: 'MVP release',
                description: 'Phase 1',
                status: 'active',
                start_date: '2026-04-01',
                due_date: '2026-04-14',
                sort_order: 1,
                progress: 0.5,
                issue_count: 2,
                completed_issue_count: 0,
                updated_at: '2026-04-05T09:00:00',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }),
        );
      }
      if (url.includes('/api/v1/pms/projects/project-1/issues')) {
        return Promise.resolve(
          jsonResponse({
            items: [
              {
                id: 'issue-1',
                project_id: 'project-1',
                reference: 'AID-1',
                title: 'Project dashboard',
                description: 'Add summary cards',
                status: 'backlog',
                status_label: 'Backlog',
                priority: 'high',
                priority_label: 'High',
                assignee_id: 'user-1',
                assignee_name: 'AIDOO Admin',
                reporter_id: 'user-1',
                reporter_name: 'AIDOO Admin',
                milestone_id: 'milestone-1',
                milestone_title: 'MVP release',
                start_date: '2026-04-06',
                due_date: '2026-04-09',
                board_position: 1,
                archived: false,
                progress: 0,
                comments_count: 1,
                labels: [],
                updated_at: '2026-04-05T09:00:00',
              },
              {
                id: 'issue-2',
                project_id: 'project-1',
                reference: 'AID-2',
                title: 'Issue drawer',
                description: 'Support detail view',
                status: 'todo',
                status_label: 'Todo',
                priority: 'medium',
                priority_label: 'Medium',
                assignee_id: 'user-1',
                assignee_name: 'AIDOO Admin',
                reporter_id: 'user-1',
                reporter_name: 'AIDOO Admin',
                milestone_id: 'milestone-1',
                milestone_title: 'MVP release',
                start_date: '2026-04-06',
                due_date: '2026-04-11',
                board_position: 1,
                archived: false,
                progress: 0,
                comments_count: 0,
                labels: [],
                updated_at: '2026-04-05T09:00:00',
              },
            ],
            total: 2,
            page: 1,
            page_size: 100,
          }),
        );
      }
      throw new Error(`Unhandled fetch for ${url}`);
    });
  });

  afterEach(() => {
    flushSync(() => {
      root.unmount();
    });
    container.remove();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('should render successfully', async () => {
    await renderApp();
    await settle();
    expect(container).toBeTruthy();
  });

  it('should render the portal heading', async () => {
    await renderApp();
    await settle();
    expect(findElementByText(/아이두 통합검색/i)).toBeTruthy();
    expect(window.location.pathname).toBe('/search');
  });

  it('should navigate to the draft workspace from the legacy sidebar menu', async () => {
    await renderApp();
    await settle();

    clickMatchingElement(/기안작성 도우미/i);
    await settle();

    expect(findElementByText(/기안작성 도우미/i)).toBeTruthy();
    expect(findElementByText(/초안 큐/i)).toBeTruthy();
    expect(window.location.pathname).toBe('/drafteditor');
  });

  it('should log out back to the login screen', async () => {
    await renderApp();
    await settle();

    clickMatchingElement(/로그아웃/i);
    await settle();

    expect(findElementByText(/로그인/i)).toBeTruthy();
    expect(findElementByText(/등록된 자체 계정으로 업무 포털에 로그인합니다\./i)).toBeTruthy();
    expect(findElementByText(/AIDOO Admin/i)).toBeNull();
  });

  it('should show setup mode when bootstrap is required', async () => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/bootstrap-status')) {
        return Promise.resolve(jsonResponse({ requires_setup: true }));
      }
      throw new Error(`Unhandled fetch for ${url}`);
    });
    await renderApp();
    await settle();

    expect(findElementByText(/첫 관리자 계정 생성/i)).toBeTruthy();
  });

  it('should render the PLM workspace when the pathname points to /plm', async () => {
    window.history.replaceState({}, '', '/plm');
    await renderApp();
    await settle();

    expect(findElementByText(/PLM 조회 작업면/i)).toBeTruthy();
    expect(findElementByText(/승인된 조회 템플릿/i)).toBeTruthy();
  });

  it('should normalize the legacy documents path to /search', async () => {
    window.history.replaceState({}, '', '/documents');
    await renderApp();
    await settle();

    expect(findElementByText(/아이두 통합검색/i)).toBeTruthy();
    expect(window.location.pathname).toBe('/search');
  });

  it('should render the meeting migration page when the pathname points to /meeting', async () => {
    window.history.replaceState({}, '', '/meeting');
    await renderApp();
    await settle();

    expect(findElementByText(/회의록/i)).toBeTruthy();
    expect(findElementByText(/WhisperX STT/i)).toBeTruthy();
  });

  it('should render the PMS workspace when the pathname points to /pms', async () => {
    window.history.replaceState({}, '', '/pms');
    await renderApp();
    await settle();
    await settle();

    expect(findElementByText(/PMS 프로젝트 관리/i)).toBeTruthy();
    expect(findElementByText(/프로젝트/i)).toBeTruthy();
  });
});
