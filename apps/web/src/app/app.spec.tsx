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

  function clickMatchingElement(text: RegExp, selector = 'button, [role="button"], tr') {
    const element = findElementByText(text);
    const clickable = element?.closest<HTMLElement>(selector) ?? element;
    clickable?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    window.history.replaceState({}, '', '/');
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
    expect(findElementByText(/아이두 AI 업무 포털/i)).toBeTruthy();
    expect(window.location.pathname).toBe('/documents');
  });

  it('should open the document detail drawer from the shared data table', async () => {
    await renderApp();
    await settle();

    expect(findElementByText(/citation required/i)).toBeNull();
    clickMatchingElement(/Seal Material Change Notice/i);
    await settle();

    expect(findElementByText(/citation required/i)).toBeTruthy();
    expect(findElementByText(/초안에 근거 추가/i)).toBeTruthy();
  });

  it('should log out back to the login screen', async () => {
    await renderApp();
    await settle();

    clickMatchingElement(/로그아웃/i);
    await settle();

    expect(findElementByText(/로그인/i)).toBeTruthy();
    expect(findElementByText(/등록된 자체 계정으로 아이두에 로그인합니다\./i)).toBeTruthy();
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
});
