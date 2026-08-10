import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';

import type {
  PatentPriorArtReportFormat,
  PatentPriorArtResult,
} from '../api/patent-prior-art-api';
import { PatentPriorArtResultPanel } from './PatentPriorArtResultPanel';

const reportFormats = [
  'html',
  'pdf',
  'docx',
  'summary_pdf',
  'summary_docx',
] as const satisfies readonly PatentPriorArtReportFormat[];

const result: PatentPriorArtResult = {
  artifacts: [
    {
      filename: 'result.json',
      id: 'result-json',
      kind: 'result_json',
      mime_type: 'application/json',
      size_bytes: 120,
    },
    {
      filename: 'report.md',
      id: 'report-markdown',
      kind: 'report_markdown',
      mime_type: 'text/markdown',
      size_bytes: 240,
    },
  ],
  candidate_count: 0,
  candidates: [],
  executed_queries: [],
  job: {
    automatic_restart_count: 0,
    can_cancel: false,
    created_at: '2026-07-22T01:00:00Z',
    execution_attempts: 0,
    id: 'job-1',
    progress_percent: 100,
    stage: '',
    status: 'succeeded',
    title: 'Research',
    updated_at: '2026-07-22T01:10:00Z',
  },
  partial: false,
  report_markdown: '',
};

describe('PatentPriorArtResultPanel', () => {
  it('renders all report actions in config order while retaining artifacts', () => {
    const onDownload = vi.fn();
    const onDownloadReport = vi.fn();
    render(
      <PatentPriorArtResultPanel
        busy={false}
        onDownload={onDownload}
        onDownloadReport={onDownloadReport}
        reportFormats={reportFormats}
        result={result}
      />,
    );

    const reportsHeading = screen.getByRole('heading', {
      name: i18n.t('ai.patentPriorArt.reports.title', { ns: 'apps' }),
    });
    const reportsSection = reportsHeading.closest('section');
    expect(reportsSection).not.toBeNull();
    const reportButtons = within(reportsSection as HTMLElement).getAllByRole(
      'button',
    );

    expect(reportButtons).toHaveLength(5);
    expect(reportButtons.map((button) => button.textContent?.trim())).toEqual(
      reportFormats.map((reportFormat) =>
        i18n.t(`ai.patentPriorArt.reports.${reportFormat}`, { ns: 'apps' }),
      ),
    );
    reportButtons.forEach((button) => fireEvent.click(button));
    expect(
      onDownloadReport.mock.calls.map(([reportFormat]) => reportFormat),
    ).toEqual(reportFormats);

    for (const artifact of result.artifacts ?? []) {
      fireEvent.click(
        screen.getByRole('button', {
          name: new RegExp(
            i18n.t(`ai.patentPriorArt.artifacts.${artifact.kind}`, {
              ns: 'apps',
            }),
          ),
        }),
      );
    }
    expect(onDownload).toHaveBeenCalledTimes(2);
  });

  it('shows a translated partial-result warning and the failed search scope', () => {
    const partialResult: PatentPriorArtResult = {
      ...result,
      executed_queries: [
        {
          failure_code: 'provider_timeout',
          jurisdiction: 'WO',
          query_text: 'heat exchanger',
          result_count: null,
          source_id: 'kipris',
          source_label: 'KIPRIS',
          status: 'failed',
        },
      ],
      partial: true,
    };

    render(
      <PatentPriorArtResultPanel
        busy={false}
        onDownload={vi.fn()}
        onDownloadReport={vi.fn()}
        reportFormats={[]}
        result={partialResult}
      />,
    );

    expect(
      screen.getByText(
        i18n.t('ai.patentPriorArt.results.partialTitle', { ns: 'apps' }),
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        i18n.t('ai.patentPriorArt.results.failedScopeItem', {
          jurisdiction: 'WO',
          ns: 'apps',
          source: 'KIPRIS',
        }),
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        i18n.t('ai.patentPriorArt.results.queryFailures.provider_timeout', {
          ns: 'apps',
        }),
      ),
    ).toBeTruthy();

    const queryRow = screen.getByText('heat exchanger').closest('tr');
    expect(queryRow).not.toBeNull();
    expect(
      within(queryRow as HTMLElement).getByText(
        i18n.t('ai.patentPriorArt.results.queryStatuses.failed', {
          ns: 'apps',
        }),
      ),
    ).toBeTruthy();
  });
});
