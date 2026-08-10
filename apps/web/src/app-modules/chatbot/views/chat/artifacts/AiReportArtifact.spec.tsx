import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AiReportArtifact } from './AiReportArtifact';

const mocks = vi.hoisted(() => ({
  downloadBlobAsFile: vi.fn(),
  getAiArtifact: vi.fn(),
  listAiArtifactSources: vi.fn(),
}));

vi.mock('@/src/platform/browser/browser-download', () => ({
  downloadBlobAsFile: mocks.downloadBlobAsFile,
}));

vi.mock('../../../api/ai-artifacts-api', () => ({
  getAiArtifact: mocks.getAiArtifact,
  listAiArtifactSources: mocks.listAiArtifactSources,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token' }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      ({
        'ai.artifacts.reportDetail.tabs.label': '보고서 상세',
        'ai.artifacts.reportDetail.tabs.report': '보고서',
        'ai.artifacts.reportDetail.tabs.sources': '사용 데이터',
        'ai.artifacts.reportDetail.numberLabel': '보고서 번호',
        'ai.artifacts.reportDetail.download.numberLabel': '보고서 번호',
        'ai.artifacts.reportDetail.download.completedAtLabel': '완료 시각',
        'ai.artifacts.reportDetail.sources.empty':
          '보고서 작성에 사용된 데이터가 없습니다.',
        'ai.artifacts.reportDetail.sources.loadFailed':
          '사용 데이터를 불러오지 못했습니다.',
        'ai.artifacts.reportDetail.sources.noRows':
          '표시할 데이터 행이 없습니다.',
        'ai.artifacts.reportDetail.sources.rowCount': `${options?.count ?? 0}건`,
        'ai.artifacts.reportDetail.sources.untitled': '사용 데이터',
        'ai.artifacts.downloadMarkdown': 'Markdown 다운로드',
      })[key] ?? key,
  }),
}));

describe('AiReportArtifact', () => {
  beforeEach(() => {
    mocks.downloadBlobAsFile.mockReset();
    mocks.getAiArtifact.mockReset();
    mocks.listAiArtifactSources.mockReset();
    mocks.getAiArtifact.mockResolvedValue({
      id: 'report-1',
      artifactNumber: 'AIR-20260726-0000000001',
      graphRunId: 'run-1',
      conversationId: 'conversation-1',
      conversationTurnId: 'turn-1',
      kind: 'report',
      status: 'completed',
      title: '접속 오류 보고서',
      contentMarkdown: '# 최종 보고서\n접속 오류를 요약했습니다.',
      createdAt: '2026-07-26T01:00:00Z',
      completedAt: '2026-07-26T01:01:00Z',
    });
    mocks.listAiArtifactSources.mockResolvedValue([
      {
        id: 'source-1',
        sourceKind: 'query_result',
        title: '지역별 오류 발생',
        columns: [
          { key: 'region', label: '지역' },
          { key: 'count', label: '건수' },
        ],
        rows: [{ region: '서울', count: 12 }],
        rowCount: 1,
        truncated: false,
        queryId: 'regional-error-count',
      },
    ]);
  });

  it('opens the final report first and renders source rows under Data used', async () => {
    renderReport();

    expect(await screen.findByText('AIR-20260726-0000000001')).toBeTruthy();
    const reportTab = screen.getByRole('tab', { name: '보고서' });
    expect(reportTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('heading', { name: '최종 보고서' })).toBeTruthy();

    await waitFor(() => {
      expect(mocks.listAiArtifactSources).toHaveBeenCalled();
    });
    const sourcesTab = screen.getByRole('tab', { name: '사용 데이터' });
    fireEvent.mouseDown(sourcesTab, { button: 0, ctrlKey: false });

    expect(
      await screen.findByRole('heading', { name: '지역별 오류 발생' }),
    ).toBeTruthy();
    expect(screen.getByRole('columnheader', { name: '지역' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '서울' })).toBeTruthy();
    expect(screen.getByRole('cell', { name: '12' })).toBeTruthy();
    expect(screen.queryByText('query_result')).toBeNull();
    expect(screen.queryByText('regional-error-count')).toBeNull();
  });

  it('downloads the immutable report with its report number metadata', async () => {
    renderReport();

    fireEvent.click(
      await screen.findByRole('button', { name: 'Markdown 다운로드' }),
    );

    expect(mocks.downloadBlobAsFile).toHaveBeenCalledTimes(1);
    const [blob, filename] = mocks.downloadBlobAsFile.mock.calls[0] as [
      Blob,
      string,
    ];
    expect(filename).toBe('AIR-20260726-0000000001_접속-오류-보고서.md');
    expect(await readBlobText(blob)).toBe(
      '보고서 번호: AIR-20260726-0000000001\n' +
        '완료 시각: 2026-07-26T01:01:00Z\n\n' +
        '# 최종 보고서\n접속 오류를 요약했습니다.',
    );
  });

  it('shows a load error instead of claiming that report sources are empty', async () => {
    mocks.getAiArtifact.mockRejectedValue(new Error('network unavailable'));

    renderReport();

    const sourcesTab = screen.getByRole('tab', { name: '사용 데이터' });
    fireEvent.mouseDown(sourcesTab, { button: 0, ctrlKey: false });

    expect((await screen.findByRole('alert')).textContent).toContain(
      '사용 데이터를 불러오지 못했습니다.',
    );
    expect(
      screen.queryByText('보고서 작성에 사용된 데이터가 없습니다.'),
    ).toBeNull();
  });

  it('keeps ordinary document artifacts on the plain document renderer', async () => {
    mocks.getAiArtifact.mockResolvedValue({
      id: 'document-1',
      artifactNumber: 2,
      graphRunId: 'run-2',
      conversationId: 'conversation-1',
      conversationTurnId: 'turn-2',
      kind: 'analysis',
      status: 'completed',
      title: '메모',
      contentMarkdown: '# 일반 문서',
      createdAt: null,
      completedAt: null,
    });

    renderReport({
      id: 'document-1',
      kind: null,
      content: '# 일반 문서',
    });

    expect(
      await screen.findByRole('heading', { name: '일반 문서' }),
    ).toBeTruthy();
    expect(screen.queryByRole('tab', { name: '보고서' })).toBeNull();
  });
});

function readBlobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener('load', () => resolve(String(reader.result ?? '')));
    reader.addEventListener('error', () => reject(reader.error));
    reader.readAsText(blob);
  });
}

function renderReport(
  overrides: Partial<Parameters<typeof AiReportArtifact>[0]['artifact']> = {},
) {
  const artifact = {
    id: 'report-1',
    type: 'document',
    title: '접속 오류 보고서',
    language: null,
    content: '# 최종 보고서\n초기 내용',
    status: 'closed' as const,
    kind: 'report',
    ...overrides,
  };
  return render(
    <MemoryRouter initialEntries={['/w/research/docs/assistant']}>
      <Routes>
        <Route
          path="/w/:workspaceSlug/docs/assistant"
          element={<AiReportArtifact artifact={artifact} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}
