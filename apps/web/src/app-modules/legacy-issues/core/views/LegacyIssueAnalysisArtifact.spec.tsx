import { render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  LegacyIssueAnalysisArtifact,
  parseLegacyIssueAnalysisPayload,
} from './LegacyIssueAnalysisArtifact';

vi.mock('@ai-do/ui', () => ({
  BarChartCard: ({
    categories,
    series,
    title,
  }: {
    categories: string[];
    series: Array<{ label: string }>;
    title: ReactNode;
  }) => (
    <div data-testid="bar-chart">
      {title}
      {categories.join('|')}
      {series.map((item) => item.label).join('|')}
    </div>
  ),
  LineChartCard: ({
    categories,
    series,
    title,
  }: {
    categories: string[];
    series: Array<{ label: string }>;
    title: ReactNode;
  }) => (
    <div data-testid="line-chart">
      {title}
      {categories.join('|')}
      {series.map((item) => item.label).join('|')}
    </div>
  ),
}));

describe('LegacyIssueAnalysisArtifact', () => {
  it('renders scalar values, warnings, and coverage from server labels', () => {
    render(
      <LegacyIssueAnalysisArtifact
        content={payload({
          warnings: ['전체 범위 경고'],
          queries: [
            query({
              id: 'count',
              title: '과거차 전체 건수',
              shape: 'scalar',
              columns: [
                {
                  key: 'issue_count',
                  label: '전체 건수',
                  type: 'number',
                  role: 'metric',
                },
              ],
              rows: [{ issue_count: 979 }],
              coverage: [
                {
                  field_key: 'vehicle_model',
                  label: '차종',
                  present_count: 900,
                  missing_count: 70,
                  invalid_count: 9,
                },
              ],
              warnings: ['일부 모듈 경고'],
            }),
          ],
        })}
      />,
    );

    expect(screen.getByRole('heading', { name: '과거차 분석' })).toBeTruthy();
    expect(screen.getByText('전체 범위 경고')).toBeTruthy();
    expect(screen.getByText('일부 모듈 경고')).toBeTruthy();
    expect(screen.getByText('전체 건수')).toBeTruthy();
    expect(screen.getByText('979')).toBeTruthy();
    expect(screen.getByText('차종')).toBeTruthy();
    expect(screen.getByText('900 / 70 / 9')).toBeTruthy();
  });

  it('maps bar and time-series shapes to chart series while retaining accessible tables', () => {
    render(
      <LegacyIssueAnalysisArtifact
        content={payload({
          queries: [
            query({
              id: 'region',
              title: '권역별 건수',
              shape: 'bar',
              columns: [
                {
                  key: 'region',
                  label: '권역',
                  type: 'text',
                  role: 'dimension',
                },
                {
                  key: 'count',
                  label: '건수',
                  type: 'number',
                  role: 'metric',
                },
              ],
              rows: [
                { region: '국내', count: 50 },
                { region: '해외', count: 23 },
              ],
            }),
            query({
              id: 'trend',
              title: '월별 추이',
              shape: 'time_series',
              columns: [
                {
                  key: 'month',
                  label: '월',
                  type: 'date',
                  role: 'dimension',
                },
                {
                  key: 'count',
                  label: '건수',
                  type: 'number',
                  role: 'metric',
                },
              ],
              rows: [{ month: '2026-06', count: 12 }],
            }),
          ],
        })}
      />,
    );

    expect(screen.getByTestId('bar-chart').textContent).toContain(
      '국내|해외건수',
    );
    expect(screen.getByTestId('line-chart').textContent).toContain(
      '2026-06건수',
    );
    const accessibleTables = screen.getAllByRole('table', { hidden: true });
    expect(accessibleTables).toHaveLength(2);
    expect(
      within(accessibleTables[0]).getByRole('columnheader', {
        hidden: true,
        name: '권역',
      }),
    ).toBeTruthy();
  });

  it('renders crosstab rows and detail records without inventing labels', () => {
    render(
      <LegacyIssueAnalysisArtifact
        content={payload({
          queries: [
            query({
              id: 'matrix',
              title: '권역 차종 교차표',
              shape: 'crosstab',
              columns: [
                {
                  key: 'region',
                  label: '권역',
                  type: 'text',
                  role: 'dimension',
                },
                {
                  key: 'vehicle',
                  label: '차종',
                  type: 'text',
                  role: 'dimension',
                },
                {
                  key: 'count',
                  label: '건수',
                  type: 'number',
                  role: 'metric',
                },
              ],
              rows: [{ region: '국내', vehicle: 'HX', count: 7 }],
            }),
            query({
              id: 'records',
              title: '상세 결과',
              shape: 'detail',
              columns: [
                {
                  key: 'model',
                  label: '차종',
                  type: 'text',
                  role: 'dimension',
                },
                {
                  key: 'issue',
                  label: '문제점',
                  type: 'text',
                  role: 'dimension',
                },
              ],
              rows: [{ model: 'HX', issue: '간헐 소음' }],
            }),
          ],
        })}
      />,
    );

    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.getByText('간헐 소음')).toBeTruthy();
    expect(screen.getAllByText('차종')).toHaveLength(2);
  });

  it('shows mixed source counts separately instead of a combined population', () => {
    render(
      <LegacyIssueAnalysisArtifact
        content={payload({
          scope: {
            dataset_key: 'common-master',
            data_sources: ['legacy_issues', 'vehicle_checklists'],
            module_keys: ['master'],
            revision_ids: ['revision-1'],
            checklist_ids: ['checklist-1'],
            source_counts: {
              legacy_issues: 979,
              vehicle_checklists: 3,
            },
          },
          queries: [
            query({
              data_source: 'vehicle_checklists',
              source_count: 3,
            }),
          ],
        })}
      />,
    );

    expect(screen.getByText('common-master · 979')).toBeTruthy();
    expect(screen.getAllByText('항목 수 · 3')).toHaveLength(2);
    expect(screen.queryByText('common-master · 982')).toBeNull();
  });

  it('falls back to raw preformatted content for invalid or unknown versions', () => {
    const invalid = '{"version":2,"title":"future"}';
    const { container } = render(
      <LegacyIssueAnalysisArtifact content={invalid} />,
    );

    expect(container.querySelector('pre')?.textContent).toBe(invalid);
    expect(parseLegacyIssueAnalysisPayload(invalid)).toEqual({ ok: false });
    expect(parseLegacyIssueAnalysisPayload('{')).toEqual({ ok: false });
  });

  it('rejects mixed-source payloads with combined or missing provenance', () => {
    const invalidMixed = payload({
      scope: {
        dataset_key: 'common-master',
        data_sources: ['legacy_issues', 'vehicle_checklists'],
        module_keys: ['master'],
        revision_ids: ['revision-1'],
        source_count: 982,
      },
      queries: [query({})],
    });

    expect(parseLegacyIssueAnalysisPayload(invalidMixed)).toEqual({
      ok: false,
    });
  });
});

function payload(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    version: 1,
    mode: 'analytics',
    title: '과거차 분석',
    exactness: 'exact',
    scope: {
      dataset_key: 'common-master',
      module_keys: ['master'],
      revision_ids: ['revision-1'],
      source_count: 979,
    },
    queries: [],
    ...overrides,
  });
}

function query(overrides: Record<string, unknown>) {
  return {
    id: 'query-1',
    title: '분석 결과',
    family_id: 'total_count',
    family_version: 1,
    shape: 'table',
    exactness: 'exact',
    columns: [],
    rows: [],
    truncated: false,
    ...overrides,
  };
}
