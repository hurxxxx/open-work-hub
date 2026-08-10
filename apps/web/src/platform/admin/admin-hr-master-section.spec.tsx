import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { i18n } from '@/src/platform/i18n';

import {
  createAdminHrManualMatch,
  getAdminHrEmployee,
  getAdminHrMasterStatus,
  listAdminHrManualMatchCandidates,
  listAdminHrEmployees,
  listAdminHrWorkforceCategories,
  revokeAdminHrManualMatch,
  type AdminHrEmployeeDetail,
  type AdminHrEmployeesResponse,
} from './admin-api';
import { AdminHrMasterSection } from './admin-hr-master-section';

vi.mock('./admin-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./admin-api')>();
  return {
    ...actual,
    getAdminHrEmployee: vi.fn(),
    getAdminHrMasterStatus: vi.fn(),
    listAdminHrEmployees: vi.fn(),
    revokeAdminHrManualMatch: vi.fn(),
    createAdminHrManualMatch: vi.fn(),
    listAdminHrManualMatchCandidates: vi.fn(),
    listAdminHrWorkforceCategories: vi.fn(),
  };
});

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

const listEmployeesMock = vi.mocked(listAdminHrEmployees);
const revokeManualMatchMock = vi.mocked(revokeAdminHrManualMatch);
const getEmployeeMock = vi.mocked(getAdminHrEmployee);
const getMasterStatusMock = vi.mocked(getAdminHrMasterStatus);
const createManualMatchMock = vi.mocked(createAdminHrManualMatch);
const listManualMatchCandidatesMock = vi.mocked(
  listAdminHrManualMatchCandidates,
);
const listWorkforceCategoriesMock = vi.mocked(listAdminHrWorkforceCategories);

const workforceCategories = [
  {
    code: 'internal',
    name: '일반 인력',
    description: 'ERP와 그룹웨어에 모두 존재',
    is_system: true,
    is_active: true,
    sort_order: 10,
    created_at: '2026-07-29T03:00:00Z',
    updated_at: '2026-07-29T03:00:00Z',
  },
  {
    code: 'unresolved',
    name: '확인 필요',
    description: '매핑 확인 필요',
    is_system: true,
    is_active: true,
    sort_order: 40,
    created_at: '2026-07-29T03:00:00Z',
    updated_at: '2026-07-29T03:00:00Z',
  },
];

const successfulRun = {
  id: 'master-run-1',
  status: 'succeeded' as const,
  completed_at: '2026-07-29T03:30:00Z',
  source_erp_run_id: 'erp-run-1',
  source_groupware_run_id: 'gw-run-1',
  identity_resolution_revision: 0,
  error_code: null,
};

const listResponse: AdminHrEmployeesResponse = {
  latest_run: successfulRun,
  status_counts: {
    matched: 1,
    erp_only: 0,
    groupware_only: 0,
    identity_conflict: 0,
  },
  workforce_counts: {
    internal: 1,
    field: 0,
    external: 0,
    unresolved: 0,
  },
  items: [
    {
      record_id: 'record-1',
      record_kind: 'person',
      employee_code: 'E100',
      name: '홍길동',
      group_code: 'RND',
      group_name: '연구개발',
      group_source: 'erp',
      position: '책임',
      occupation: '연구',
      email: 'canonical@example.com',
      has_erp: true,
      has_groupware: true,
      reconciliation_status: 'matched',
      inferred_workforce_category: 'internal',
      workforce_category: 'internal',
      workforce_category_resolution_kind: 'inferred',
      workforce_assignment_id: null,
      identity_resolution_kind: 'employee_code',
      applied_at: '2026-07-29T03:30:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  groups: [
    {
      code: 'RND',
      name: '연구개발',
      source: 'erp',
    },
  ],
};

const detailResponse: AdminHrEmployeeDetail = {
  ...listResponse.items[0],
  erp: {
    employee_code: 'E100',
    name: '홍길동',
    group_code: 'RND',
    group_name: '연구개발',
    position: '책임',
    occupation: '연구',
    email: 'erp@example.com',
  },
  groupware: {
    employee_code: 'E100',
    name: '홍길동',
    group_code: 'GW-RND',
    group_name: '기술연구소',
    email: 'gw@example.com',
    login_id: 'hong',
  },
  conflict_reasons: [],
  match_candidates: [],
  provenance: {
    master_run_id: 'master-run-1',
    erp_run_id: 'erp-run-1',
    groupware_run_id: 'gw-run-1',
  },
};

describe('AdminHrMasterSection', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('ko-KR');
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    listEmployeesMock.mockReset();
    revokeManualMatchMock.mockReset();
    getEmployeeMock.mockReset();
    getMasterStatusMock.mockReset();
    createManualMatchMock.mockReset();
    listManualMatchCandidatesMock.mockReset();
    listWorkforceCategoriesMock.mockReset();
    listEmployeesMock.mockResolvedValue(listResponse);
    getEmployeeMock.mockResolvedValue(detailResponse);
    getMasterStatusMock.mockResolvedValue({
      latest_succeeded: successfulRun,
      latest_attempt: {
        ...successfulRun,
        id: 'master-run-building',
        status: 'building',
        completed_at: null,
        identity_resolution_revision: 1,
      },
    });
    listWorkforceCategoriesMock.mockResolvedValue({
      items: workforceCategories,
    });
    listManualMatchCandidatesMock.mockImplementation(async (_token, query) => ({
      master_run_id: 'master-run-1',
      source: query.source,
      items:
        query.source === 'erp'
          ? [
              {
                record_id: 'erp-record',
                employee_code: 'E200',
                name: 'ERP 사용자',
                group_name: '연구개발',
              },
            ]
          : [
              {
                record_id: 'groupware-record',
                employee_code: 'G200',
                name: '그룹웨어 사용자',
                group_name: '기술연구소',
                login_id: 'gw-user',
              },
            ],
      total: 1,
      page: query.page ?? 1,
      page_size: query.page_size ?? 12,
    }));
    createManualMatchMock.mockResolvedValue({
      link_id: 'link-1',
      identity_resolution_revision: 1,
      rebuild_queued: true,
      rebuild_task_id: 'task-1',
    });
    revokeManualMatchMock.mockResolvedValue({
      link_id: 'link-1',
      identity_resolution_revision: 2,
      rebuild_queued: true,
      rebuild_task_id: 'task-2',
    });
  });

  it('renders the read-only canonical grid and safe ERP/groupware detail', async () => {
    render(<AdminHrMasterSection token="token" />);

    expect(await screen.findAllByText('홍길동')).not.toHaveLength(0);
    expect(screen.getAllByText('E100')).not.toHaveLength(0);
    expect(screen.getAllByText('연구개발')).not.toHaveLength(0);
    expect(
      screen.getByRole('button', {
        name: 'ERP · 그룹웨어 사용자 매핑',
      }),
    ).toBeTruthy();

    const desktopName = screen
      .getAllByText('홍길동')
      .find((element) => element.closest('tr'));
    if (!desktopName) {
      throw new Error('desktop HR grid row is required');
    }
    fireEvent.click(desktopName.closest('tr') as HTMLTableRowElement);

    expect(await screen.findByText('erp@example.com')).toBeTruthy();
    expect(screen.getByText('gw@example.com')).toBeTruthy();
    expect(screen.getByText('hong')).toBeTruthy();
    expect(screen.getByText('master-run-1')).toBeTruthy();
    expect(screen.queryByText('900101-1234567')).toBeNull();
    expect(getEmployeeMock).toHaveBeenCalledWith('token', 'record-1');
  });

  it('debounces search before requesting the server-filtered first page', async () => {
    render(<AdminHrMasterSection token="token" />);
    await screen.findAllByText('홍길동');

    fireEvent.change(screen.getByLabelText('통합 인사정보 검색'), {
      target: { value: ' E200 ' },
    });

    await waitFor(() => {
      expect(listEmployeesMock).toHaveBeenLastCalledWith(
        'token',
        expect.objectContaining({
          page: 1,
          page_size: 20,
          q: 'E200',
        }),
      );
    });
  });

  it('filters the directory to manually mapped users', async () => {
    render(<AdminHrMasterSection token="token" />);
    await screen.findAllByText('홍길동');

    fireEvent.click(screen.getByRole('combobox', { name: '매핑 상태' }));
    fireEvent.click(await screen.findByRole('option', { name: '수동 매칭' }));

    await waitFor(() => {
      expect(listEmployeesMock).toHaveBeenLastCalledWith(
        'token',
        expect.objectContaining({
          identity_resolution_kind: 'manual',
        }),
      );
    });
  });

  it('lets an administrator directly select and map differently named users', async () => {
    const candidateDetail: AdminHrEmployeeDetail = {
      ...detailResponse,
      record_id: 'groupware-record',
      employee_code: 'G200',
      name: '그룹웨어 사용자',
      has_erp: false,
      has_groupware: true,
      reconciliation_status: 'groupware_only',
      inferred_workforce_category: 'unresolved',
      workforce_category: 'unresolved',
      workforce_category_resolution_kind: 'inferred',
      identity_resolution_kind: 'none',
      erp: null,
      groupware: {
        employee_code: 'G200',
        name: '그룹웨어 사용자',
        group_name: '기술연구소',
        login_id: 'gw-user',
      },
      match_candidates: [],
    };
    getEmployeeMock.mockResolvedValue(candidateDetail);

    render(<AdminHrMasterSection token="token" />);
    const desktopName = (await screen.findAllByText('홍길동')).find((element) =>
      element.closest('tr'),
    );
    fireEvent.click(desktopName?.closest('tr') as HTMLTableRowElement);
    fireEvent.click(
      await screen.findByRole('button', { name: '연결할 사용자 선택' }),
    );
    fireEvent.click(await screen.findByRole('button', { name: /ERP 사용자/ }));
    fireEvent.change(screen.getByLabelText('확인 사유'), {
      target: { value: '인사팀 확인 완료' },
    });
    fireEvent.click(screen.getByRole('button', { name: '선택 사용자 연결' }));

    await waitFor(() => {
      expect(createManualMatchMock).toHaveBeenCalledWith('token', {
        master_run_id: 'master-run-1',
        groupware_record_id: 'groupware-record',
        erp_record_id: 'erp-record',
        reason: '인사팀 확인 완료',
      });
    });
    expect(
      await screen.findAllByText(
        '사용자 매핑을 저장했고 새 통합본 생성을 요청했습니다.',
      ),
    ).not.toHaveLength(0);
  });

  it('stops waiting and reports a failed unified projection build', async () => {
    getMasterStatusMock.mockResolvedValue({
      latest_succeeded: successfulRun,
      latest_attempt: {
        ...successfulRun,
        id: 'master-run-failed',
        status: 'failed',
        completed_at: '2026-07-29T03:31:00Z',
        identity_resolution_revision: 1,
        error_code: 'unexpected_build_error',
      },
    });

    render(<AdminHrMasterSection token="token" />);
    await screen.findAllByText('홍길동');
    fireEvent.click(
      screen.getByRole('button', {
        name: 'ERP · 그룹웨어 사용자 매핑',
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: /그룹웨어 사용자/ }),
    );
    fireEvent.click(await screen.findByRole('button', { name: /ERP 사용자/ }));
    fireEvent.change(screen.getByLabelText('확인 사유'), {
      target: { value: '인사팀 확인 완료' },
    });
    fireEvent.click(screen.getByRole('button', { name: '선택 사용자 연결' }));

    expect(
      await screen.findByText(
        '새 통합본 생성에 실패했습니다. 매핑은 저장되어 있으며 배치 상태를 확인한 뒤 다시 실행해 주세요.',
      ),
    ).toBeTruthy();
    expect(getMasterStatusMock).toHaveBeenCalledWith('token');
    expect(
      screen.queryByText(
        '새 통합본을 생성하고 있습니다. 완료되면 목록과 상세가 자동으로 갱신됩니다.',
      ),
    ).toBeNull();
  });

  it('revokes a manual mapping from the mapped employee detail', async () => {
    const confirmMock = vi.spyOn(window, 'confirm').mockReturnValue(true);
    getEmployeeMock.mockResolvedValue({
      ...detailResponse,
      identity_resolution_kind: 'manual',
      manual_identity_link_id: 'link-1',
    });

    render(<AdminHrMasterSection token="token" />);
    const desktopName = (await screen.findAllByText('홍길동')).find((element) =>
      element.closest('tr'),
    );
    fireEvent.click(desktopName?.closest('tr') as HTMLTableRowElement);
    fireEvent.click(
      await screen.findByRole('button', { name: '수동 매칭 해제' }),
    );

    await waitFor(() => {
      expect(revokeManualMatchMock).toHaveBeenCalledWith('token', 'link-1', {
        master_run_id: 'master-run-1',
      });
    });
    expect(
      await screen.findAllByText(
        '수동 매칭을 해제했고 새 통합본 생성을 요청했습니다.',
      ),
    ).not.toHaveLength(0);
    confirmMock.mockRestore();
  });
});
