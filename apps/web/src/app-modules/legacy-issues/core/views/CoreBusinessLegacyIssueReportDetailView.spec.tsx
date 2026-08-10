import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CoreBusinessLegacyIssueReportDetailView } from './CoreBusinessLegacyIssueReportDetailView';

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
  download: vi.fn(),
  getDetail: vi.fn(),
  getRows: vi.fn(),
  listQueries: vi.fn(),
  listSources: vi.fn(),
  share: vi.fn(),
  unshare: vi.fn(),
}));

const translations: Record<string, string> = {
  'common:feedback.loading': '불러오는 중...',
  'coreBusiness.reports.actions.backToList': '목록으로',
  'coreBusiness.reports.actions.download': '다운로드',
  'coreBusiness.reports.actions.openConversation': '원본 대화 열기',
  'coreBusiness.reports.actions.share': '워크스페이스에 공유',
  'coreBusiness.reports.actions.unshare': '공유 해제',
  'coreBusiness.reports.detail.queries.errorCode': '오류 코드',
  'coreBusiness.reports.detail.queries.family': '쿼리 패밀리',
  'coreBusiness.reports.detail.queries.params': '파라미터',
  'coreBusiness.reports.detail.queries.select': '조회 SQL 선택',
  'coreBusiness.reports.detail.queries.sql': 'SQL',
  'coreBusiness.reports.detail.queries.status': '상태',
  'coreBusiness.reports.detail.queries.statuses.completed': '완료',
  'coreBusiness.reports.detail.queries.statuses.failed': '실패',
  'coreBusiness.reports.detail.queries.statuses.notExecuted': '미실행',
  'coreBusiness.reports.detail.results.queryFailed':
    '실패한 SQL에는 저장된 결과가 없습니다.',
  'coreBusiness.reports.detail.results.title': '저장된 조회 결과',
  'coreBusiness.reports.detail.sources.rowCount': '1행',
  'coreBusiness.reports.detail.sources.select': '근거 선택',
  'coreBusiness.reports.detail.tabs.label': '보고서 상세',
  'coreBusiness.reports.detail.tabs.queries': 'SQL·조회 결과',
  'coreBusiness.reports.detail.tabs.report': '보고서',
  'coreBusiness.reports.detail.tabs.sources': '의미검색 근거',
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

vi.mock('@/src/platform/browser/browser-download', () => ({
  downloadBlobAsFile: mocks.download,
}));

vi.mock('@/src/components/artifacts/DocumentArtifact', () => ({
  DocumentArtifact: ({ content }: { content: string }) => (
    <div data-testid="report-document">{content}</div>
  ),
}));

vi.mock('./LegacyIssueReportDataGrid', () => ({
  LegacyIssueReportDataGrid: ({
    columns,
    rows,
  }: {
    columns: unknown[];
    rows: unknown[];
  }) => (
    <div data-testid="report-grid">
      {columns.length}:{rows.length}
    </div>
  ),
}));

vi.mock('../api/legacy-issue-assistant-report-api', () => ({
  getLegacyIssueReport: mocks.getDetail,
  getLegacyIssueReportQueryRows: mocks.getRows,
  listLegacyIssueReportQueries: mocks.listQueries,
  listLegacyIssueReportSources: mocks.listSources,
  shareLegacyIssueReport: mocks.share,
  unshareLegacyIssueReport: mocks.unshare,
}));

describe('CoreBusinessLegacyIssueReportDetailView', () => {
  beforeEach(() => {
    for (const mock of [
      mocks.getDetail,
      mocks.getRows,
      mocks.listQueries,
      mocks.listSources,
      mocks.share,
      mocks.unshare,
      mocks.download,
    ]) {
      mock.mockReset();
    }
    mocks.auth.user.id = 'user-1';
    mocks.getDetail.mockResolvedValue(reportDetail());
    mocks.listQueries.mockResolvedValue({ items: [] });
    mocks.listSources.mockResolvedValue({ items: [] });
  });

  it('shows the persisted report number and only loads tab data on demand', async () => {
    renderDetail();

    expect(await screen.findByText('결빙 문제 보고서')).toBeTruthy();
    expect(screen.getAllByText('AIR-20260727-0000000001')).toHaveLength(2);
    expect(screen.getByTestId('report-document').textContent).toContain(
      '# 결빙 문제 보고서',
    );
    expect(
      screen.getByRole('link', { name: '원본 대화 열기' }).getAttribute('href'),
    ).toBe('/w/research/legacy-issues/assistant?a=report-1&c=conversation-1');
    expect(mocks.listQueries).not.toHaveBeenCalled();
    expect(mocks.listSources).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '다운로드' }));
    expect(mocks.download).toHaveBeenCalledWith(
      expect.any(Blob),
      'AIR-20260727-0000000001_결빙-문제-보고서.md',
    );

    const sourcesTab = screen.getByRole('tab', { name: '의미검색 근거' });
    fireEvent.mouseDown(sourcesTab, { button: 0 });
    fireEvent.click(sourcesTab);
    await waitFor(() => expect(mocks.listSources).toHaveBeenCalledTimes(1));
    expect(mocks.listQueries).not.toHaveBeenCalled();
  });

  it('labels failed queries without requesting result rows or presenting zero rows', async () => {
    mocks.listQueries.mockResolvedValue({
      items: [
        {
          created_at: '2026-07-27T02:00:00Z',
          duration_ms: 10,
          error_code: 'query_failed',
          exactness: null,
          execution_status: 'failed',
          family_id: 'issue_count',
          id: 'query-1',
          ordinal: 0,
          payload_bytes: null,
          query_kind: 'sql',
          query_sha256: null,
          query_spec: null,
          result_sha256: null,
          row_count: null,
          statement_text: null,
          title: null,
          truncated: false,
          typed_params: null,
        },
      ],
    });
    renderDetail();
    await screen.findByText('결빙 문제 보고서');

    const queriesTab = screen.getByRole('tab', { name: 'SQL·조회 결과' });
    fireEvent.mouseDown(queriesTab, { button: 0 });
    fireEvent.click(queriesTab);

    expect(
      await screen.findByText('실패한 SQL에는 저장된 결과가 없습니다.'),
    ).toBeTruthy();
    expect(
      screen.getByText((_, element) => element?.textContent === '상태: 실패'),
    ).toBeTruthy();
    expect(screen.getByRole('option').textContent?.startsWith('1.')).toBe(true);
    expect(mocks.getRows).not.toHaveBeenCalled();
  });

  it('loads every captured query-result page into the read-only grid', async () => {
    mocks.listQueries.mockResolvedValue({
      items: [completedQuery()],
    });
    mocks.getRows
      .mockResolvedValueOnce({
        captured_row_count: 2,
        columns: [{ key: 'vehicle', label: '차종' }],
        limit: 1,
        offset: 0,
        query_id: 'query-1',
        row_count: 2,
        rows: [{ vehicle: 'A' }],
        total: 2,
        truncated: false,
      })
      .mockResolvedValueOnce({
        captured_row_count: 2,
        columns: [{ key: 'vehicle', label: '차종' }],
        limit: 1,
        offset: 1,
        query_id: 'query-1',
        row_count: 2,
        rows: [{ vehicle: 'B' }],
        total: 2,
        truncated: false,
      });
    renderDetail();
    await screen.findByText('결빙 문제 보고서');

    const queriesTab = screen.getByRole('tab', { name: 'SQL·조회 결과' });
    fireEvent.mouseDown(queriesTab, { button: 0 });
    fireEvent.click(queriesTab);

    expect((await screen.findByTestId('report-grid')).textContent).toContain(
      '1:2',
    );
    expect(mocks.getRows).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ offset: 1, queryId: 'query-1' }),
    );
  });

  it('does not let an old share response replace a newly opened report', async () => {
    const pendingShare = deferred<ReturnType<typeof reportDetail>>();
    mocks.share.mockReturnValue(pendingShare.promise);
    mocks.getDetail
      .mockResolvedValueOnce(reportDetail())
      .mockResolvedValueOnce({
        ...reportDetail(),
        report_id: 'report-2',
        report_number: 'AIR-20260727-0000000002',
        title: '새 보고서',
      });
    renderDetail(true);
    await screen.findByText('결빙 문제 보고서');

    fireEvent.click(
      screen.getByRole('button', { name: '워크스페이스에 공유' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'next report' }));
    expect(await screen.findByText('새 보고서')).toBeTruthy();

    pendingShare.resolve({
      ...reportDetail(),
      visibility: 'workspace',
    });
    await waitFor(() => {
      expect(screen.getByText('새 보고서')).toBeTruthy();
      expect(screen.queryByText('워크스페이스 공유')).toBeNull();
    });
  });
});

function reportDetail() {
  return {
    completed_at: '2026-07-27T02:30:00Z',
    content: '# 결빙 문제 보고서',
    content_type: 'text/markdown',
    conversation_id: 'conversation-1',
    conversation_turn_id: 'turn-1',
    created_at: '2026-07-27T02:00:00Z',
    owner_name: '작성자',
    owner_user_id: 'user-1',
    query_count: 1,
    question: '결빙 문제를 보고해줘',
    report_id: 'report-1',
    report_number: 'AIR-20260727-0000000001',
    source_count: 1,
    title: '결빙 문제 보고서',
    visibility: 'private',
  } as const;
}

function completedQuery() {
  return {
    created_at: '2026-07-27T02:00:00Z',
    duration_ms: 10,
    error_code: null,
    exactness: 'exact',
    execution_status: 'completed',
    family_id: 'issue_count',
    id: 'query-1',
    ordinal: 0,
    payload_bytes: 100,
    query_kind: 'sql',
    query_sha256: null,
    query_spec: null,
    result_sha256: null,
    row_count: 2,
    statement_text: 'SELECT vehicle FROM issues',
    title: '차종별 건수',
    truncated: false,
    typed_params: {},
  };
}

function renderDetail(withNavigation = false) {
  return render(
    <MemoryRouter
      initialEntries={[
        '/w/research/legacy-issues/reports/AIR-20260727-0000000001',
      ]}
    >
      {withNavigation ? <NavigationButton /> : null}
      <Routes>
        <Route
          path="/w/:workspaceSlug/legacy-issues/reports/:reportNumber"
          element={<CoreBusinessLegacyIssueReportDetailView />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

function NavigationButton() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() =>
        navigate('/w/research/legacy-issues/reports/AIR-20260727-0000000002')
      }
    >
      next report
    </button>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}
