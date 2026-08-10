import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CoreBusinessLegacyIssueAssistantHistoryView } from './CoreBusinessLegacyIssueAssistantHistoryView';

const mocks = vi.hoisted(() => ({
  auth: {
    token: 'token',
    user: {
      date_format: 'iso',
      id: 'user-1',
      locale: 'ko-KR',
      time_zone: 'Asia/Seoul',
    },
  },
  listReports: vi.fn(),
}));

const translations: Record<string, string> = {
  'common:feedback.loading': '불러오는 중...',
  'coreBusiness.reports.actions.refresh': '새로고침',
  'coreBusiness.reports.emptyMine': '생성한 보고서가 없습니다.',
  'coreBusiness.reports.emptyShared': '공유된 보고서가 없습니다.',
  'coreBusiness.reports.errors.listFailed':
    '보고서 목록을 불러오지 못했습니다.',
  'coreBusiness.reports.eyebrow': '과거차문제점 · AI',
  'coreBusiness.reports.listTitle': '생성된 보고서',
  'coreBusiness.reports.queryCount': 'SQL 2개',
  'coreBusiness.reports.sourceCount': '근거 1개',
  'coreBusiness.reports.title': '보고서 관리',
  'coreBusiness.reports.views.label': '보고서 구분',
  'coreBusiness.reports.views.mine': '내 보고서',
  'coreBusiness.reports.views.shared': '공유 보고서',
  'coreBusiness.reports.visibility.private': '비공개',
  'coreBusiness.reports.visibility.workspace': '워크스페이스 공유',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'ko-KR' },
    t: (key: string) => translations[key] ?? key,
  }),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => mocks.auth,
}));

vi.mock('../api/legacy-issue-assistant-report-api', () => ({
  listLegacyIssueReports: mocks.listReports,
}));

describe('CoreBusinessLegacyIssueAssistantHistoryView', () => {
  beforeEach(() => {
    mocks.auth.token = 'token';
    mocks.auth.user.id = 'user-1';
    mocks.listReports.mockReset();
    mocks.listReports.mockResolvedValue({
      items: [],
      limit: 30,
      offset: 0,
      total: 0,
    });
  });

  it('lists saved reports at the canonical report management route', async () => {
    mocks.listReports.mockResolvedValue({
      items: [reportSummary()],
      limit: 30,
      offset: 0,
      total: 1,
    });

    renderReportList();

    expect(
      await screen.findByRole('heading', { name: '보고서 관리' }),
    ).toBeTruthy();
    const link = screen.getByRole('link', { name: /결빙 문제 보고서/ });
    expect(link.getAttribute('href')).toBe(
      '/w/research/legacy-issues/reports/AIR-20260727-0000000001',
    );
    expect(screen.getByText('AIR-20260727-0000000001')).toBeTruthy();
    expect(screen.getByText('결빙 문제를 요약해줘')).toBeTruthy();
    expect(screen.getByText('비공개')).toBeTruthy();
    expect(mocks.listReports).toHaveBeenCalledWith({
      limit: 30,
      offset: 0,
      token: 'token',
      view: 'mine',
      workspaceSlug: 'research',
    });
  });

  it('loads workspace-shared reports separately and shows the owner', async () => {
    mocks.listReports
      .mockResolvedValueOnce({
        items: [],
        limit: 30,
        offset: 0,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [
          {
            ...reportSummary(),
            owner_name: '홍길동',
            visibility: 'workspace',
          },
        ],
        limit: 30,
        offset: 0,
        total: 1,
      });

    renderReportList();
    await screen.findByText('생성한 보고서가 없습니다.');
    const sharedTab = screen.getByRole('tab', { name: '공유 보고서' });
    fireEvent.mouseDown(sharedTab, { button: 0 });
    fireEvent.click(sharedTab);

    expect(await screen.findByText('홍길동')).toBeTruthy();
    expect(screen.getByText('워크스페이스 공유')).toBeTruthy();
    expect(mocks.listReports).toHaveBeenLastCalledWith({
      limit: 30,
      offset: 0,
      token: 'token',
      view: 'shared',
      workspaceSlug: 'research',
    });
  });

  it('shows loading, empty, and failure states without leaking stale data', async () => {
    const pending = deferred<{
      items: [];
      limit: number;
      offset: number;
      total: number;
    }>();
    mocks.listReports.mockReturnValueOnce(pending.promise);
    const rendered = renderReportList();

    expect((await screen.findByRole('status')).textContent).toContain(
      '불러오는 중...',
    );
    pending.resolve({ items: [], limit: 30, offset: 0, total: 0 });
    expect(await screen.findByText('생성한 보고서가 없습니다.')).toBeTruthy();

    mocks.listReports.mockRejectedValueOnce(new Error('network'));
    mocks.auth.token = 'new-token';
    mocks.auth.user.id = 'user-2';
    rendered.rerender(reportListTree());

    expect((await screen.findByRole('alert')).textContent).toContain(
      '보고서 목록을 불러오지 못했습니다.',
    );
    expect(screen.queryByText('결빙 문제 보고서')).toBeNull();
  });

  it('refreshes the active report view', async () => {
    mocks.listReports
      .mockResolvedValueOnce({
        items: [],
        limit: 30,
        offset: 0,
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [reportSummary()],
        limit: 30,
        offset: 0,
        total: 1,
      });
    renderReportList();

    await screen.findByText('생성한 보고서가 없습니다.');
    fireEvent.click(screen.getByRole('button', { name: '새로고침' }));

    expect(await screen.findByText('결빙 문제 보고서')).toBeTruthy();
    expect(mocks.listReports).toHaveBeenCalledTimes(2);
  });

  it('loads another report page with the matching offset', async () => {
    mocks.listReports
      .mockResolvedValueOnce({
        items: [reportSummary()],
        limit: 30,
        offset: 0,
        total: 31,
      })
      .mockResolvedValueOnce({
        items: [
          {
            ...reportSummary(),
            report_id: 'report-31',
            report_number: 'AIR-20260727-0000000031',
            title: '31번째 보고서',
          },
        ],
        limit: 30,
        offset: 30,
        total: 31,
      });
    renderReportList();

    await screen.findByText('결빙 문제 보고서');
    fireEvent.change(screen.getByRole('combobox', { name: '생성된 보고서' }), {
      target: { value: '2' },
    });

    expect(await screen.findByText('31번째 보고서')).toBeTruthy();
    expect(mocks.listReports).toHaveBeenLastCalledWith({
      limit: 30,
      offset: 30,
      token: 'token',
      view: 'mine',
      workspaceSlug: 'research',
    });
  });
});

function reportSummary() {
  return {
    completed_at: '2026-07-27T02:30:00Z',
    owner_name: '작성자',
    owner_user_id: 'user-1',
    preview: '결빙 관련 사례와 정형 집계를 정리했습니다.',
    query_count: 2,
    question: '결빙 문제를 요약해줘',
    report_id: 'report-1',
    report_number: 'AIR-20260727-0000000001',
    source_count: 1,
    title: '결빙 문제 보고서',
    visibility: 'private',
  };
}

function renderReportList() {
  return render(reportListTree());
}

function reportListTree() {
  return (
    <MemoryRouter initialEntries={['/w/research/legacy-issues/reports']}>
      <Routes>
        <Route
          path="/w/:workspaceSlug/legacy-issues/reports"
          element={<CoreBusinessLegacyIssueAssistantHistoryView />}
        />
      </Routes>
    </MemoryRouter>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}
