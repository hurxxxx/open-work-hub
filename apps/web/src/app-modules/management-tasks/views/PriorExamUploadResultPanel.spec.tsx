import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';

import { i18n } from '@/src/platform/i18n';
import type { HealthCheckupPriorExamUpload } from '../api/health-checkup-api';
import { PriorExamUploadResultPanel } from './PriorExamUploadResultPanel';

function uploadResult(
  overrides: Partial<HealthCheckupPriorExamUpload> = {},
): HealthCheckupPriorExamUpload {
  return {
    upload_id: 'upload-1',
    target_year: 2027,
    exam_year: 2026,
    source_filename: 'prior.xlsx',
    total_rows: 201,
    matched_count: 200,
    spouse_excluded_count: 0,
    unmatched_count: 0,
    ambiguous_count: 1,
    publish_blockers: ['unresolved_prior_exam_rows'],
    details_truncated: true,
    unmatched: [],
    matched: [],
    ...overrides,
  };
}

describe('PriorExamUploadResultPanel', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('ko-KR');
  });

  it('explains when the API omits lower-priority detail rows', () => {
    render(<PriorExamUploadResultPanel result={uploadResult()} />);

    expect(
      screen.getByText(
        '확인 필요 행을 우선 표시했으며 일부 상세 행은 생략되었습니다.',
      ),
    ).toBeTruthy();
    expect(
      screen.getByText('확인 필요 1건 (동명이인 등 · 담당자 확인)'),
    ).toBeTruthy();
    expect(screen.getByText('확정 200건')).toBeTruthy();
  });

  it('keeps aggregate-only categories visible when their details are omitted', () => {
    render(
      <PriorExamUploadResultPanel
        result={uploadResult({
          unmatched_count: 7,
        })}
      />,
    );

    expect(
      screen.getByText('제외 7건 (현직 명단에 없음 · 퇴사 등)'),
    ).toBeTruthy();
  });

  it('keeps truncated disclosure counts aligned with aggregate totals', () => {
    render(
      <PriorExamUploadResultPanel
        result={uploadResult({
          matched_count: 200,
          unmatched_count: 7,
          ambiguous_count: 3,
          unmatched: [
            {
              sheet_name: 'Sheet1',
              dept_name: '인사팀',
              person_name: '동명이인',
              raw_relation: null,
              match_status: 'ambiguous',
            },
            {
              sheet_name: 'Sheet1',
              dept_name: '퇴사자팀',
              person_name: '퇴사자',
              raw_relation: null,
              match_status: 'unmatched',
            },
          ],
          matched: [
            {
              sheet_name: 'Sheet1',
              employee_code: '100001',
              person_name: '홍길동',
              employee_name: '홍길동',
              erp_dept_name: '인사팀',
              file_dept_name: '인사팀',
            },
          ],
        })}
      />,
    );

    expect(
      screen.getByText('확인 필요 3건 (동명이인 등 · 담당자 확인)'),
    ).toBeTruthy();
    expect(
      screen.getByText('제외 7건 (현직 명단에 없음 · 퇴사 등)'),
    ).toBeTruthy();
    expect(screen.getByText('확정 200건')).toBeTruthy();
  });
});
