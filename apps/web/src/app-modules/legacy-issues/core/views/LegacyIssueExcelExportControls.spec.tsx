import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { LegacyIssueExcelExportJob } from '../api/legacy-issue-common-api';
import type { LegacyIssueExcelExportJobWorkflow } from './useLegacyIssueExcelExportJob';
import { LegacyIssueExcelExportControls } from './LegacyIssueExcelExportControls';

afterEach(async () => {
  cleanup();
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  vi.clearAllMocks();
});

describe('legacy issue Excel export controls', () => {
  it('opens a choice modal and starts a data-only export from it', async () => {
    const start = vi.fn().mockResolvedValue(undefined);
    renderControls({ busy: false, job: null, start });

    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Excel 다운로드' }));

    expect(screen.getByRole('dialog', { name: 'Excel 다운로드' })).toBeTruthy();
    expect(
      screen.getByText('다운로드할 Excel 형식을 선택해 주세요.'),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /데이터만 다운로드/ }));

    await waitFor(() => expect(start).toHaveBeenCalledWith(false));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('does not open the modal when its source is unavailable', () => {
    render(
      <LegacyIssueExcelExportControls
        disabled
        exportLabel="Excel 다운로드"
        workflow={{ busy: false, job: null, start: vi.fn() }}
      />,
    );

    const button = screen.getByRole('button', { name: 'Excel 다운로드' });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('starts an attachment-inclusive export from the modal and shows its wait state', async () => {
    const start = vi.fn().mockResolvedValue(undefined);
    const workflow = { busy: false, job: null, start };
    const rendered = renderControls(workflow);

    fireEvent.click(screen.getByRole('button', { name: 'Excel 다운로드' }));
    expect(
      screen.getByText(
        '첨부파일과 파일명을 함께 포함합니다. OLE 객체 처리로 시간이 더 걸리므로 다운로드가 시작될 때까지 기다려 주세요.',
      ),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', {
        name: /첨부파일·파일명 포함 다운로드/,
      }),
    );

    await waitFor(() => expect(start).toHaveBeenCalledWith(true));
    expect(screen.queryByRole('dialog')).toBeNull();

    rendered.rerender(
      <LegacyIssueExcelExportControls
        exportLabel="Excel 다운로드"
        workflow={{
          busy: true,
          job: exportJob({ include_attachments: true, status: 'running' }),
          start,
        }}
      />,
    );

    expect(
      (
        screen.getByRole('button', {
          name: '첨부 포함 Excel 생성 중',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(screen.getByRole('status').textContent).toBe(
      '첨부파일과 파일명을 처리하고 있습니다. 완료될 때까지 기다려 주세요.',
    );
  });

  it('closes the modal without starting an export', () => {
    const start = vi.fn();
    renderControls({ busy: false, job: null, start });

    fireEvent.click(screen.getByRole('button', { name: 'Excel 다운로드' }));
    fireEvent.click(screen.getByRole('button', { name: '닫기' }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(start).not.toHaveBeenCalled();
  });
});

function renderControls(workflow: LegacyIssueExcelExportJobWorkflow) {
  return render(
    <LegacyIssueExcelExportControls
      exportLabel="Excel 다운로드"
      workflow={workflow}
    />,
  );
}

function exportJob(
  overrides: Partial<LegacyIssueExcelExportJob> = {},
): LegacyIssueExcelExportJob {
  return {
    attachment_bytes: 8,
    attachment_count: 1,
    completed_at: null,
    created_at: '2026-07-16T00:00:00Z',
    error_code: null,
    expires_at: null,
    id: 'job-1',
    include_attachments: true,
    processed_attachment_bytes: 0,
    processed_attachment_count: 0,
    record_count: 1,
    result_filename: null,
    result_size_bytes: null,
    source_kind: 'dataset',
    status: 'queued',
    updated_at: '2026-07-16T00:00:00Z',
    ...overrides,
  };
}
