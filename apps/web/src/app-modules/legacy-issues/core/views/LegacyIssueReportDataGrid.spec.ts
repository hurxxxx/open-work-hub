import { describe, expect, it } from 'vitest';

import {
  buildLegacyIssueReportGridColumns,
  formatLegacyIssueReportGridCell,
} from './LegacyIssueReportDataGrid';

describe('LegacyIssueReportDataGrid', () => {
  it('builds stable dynamic columns and ignores duplicate declarations', () => {
    expect(
      buildLegacyIssueReportGridColumns(
        [
          { key: 'vehicle', label: '차종' },
          { key: 'vehicle', label: '중복 차종' },
          { key: 'count', label: '건수' },
        ],
        [{ count: 3, vehicle: 'GV80' }],
      ).map(({ key, title }) => ({ key, title })),
    ).toEqual([
      { key: 'vehicle', title: '차종' },
      { key: 'count', title: '건수' },
    ]);
  });

  it('derives legacy query columns from rows when stored schema is absent', () => {
    expect(
      buildLegacyIssueReportGridColumns(
        [],
        [
          { count: 1, vehicle: 'A' },
          { region: '동부', vehicle: 'B' },
        ],
      ).map((column) => column.key),
    ).toEqual(['count', 'vehicle', 'region']);
  });

  it('accepts captured SQL schemas that use name and type fields', () => {
    expect(
      buildLegacyIssueReportGridColumns(
        [
          { name: 'vehicle_model', type: 'text' },
          { name: 'issue_count', type: 'integer' },
        ],
        [{ issue_count: 3, vehicle_model: 'OV' }],
      ).map(({ key, title }) => ({ key, title })),
    ).toEqual([
      { key: 'vehicle_model', title: 'vehicle_model' },
      { key: 'issue_count', title: 'issue_count' },
    ]);
  });

  it('renders null and structured values without losing their meaning', () => {
    expect(formatLegacyIssueReportGridCell(null)).toBeNull();
    expect(formatLegacyIssueReportGridCell(false)).toBe('false');
    expect(formatLegacyIssueReportGridCell({ count: 2 })).toBe('{"count":2}');
  });
});
