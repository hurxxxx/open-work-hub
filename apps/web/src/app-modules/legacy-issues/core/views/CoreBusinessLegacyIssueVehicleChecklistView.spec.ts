import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resources } from '@/src/platform/i18n/resources';
import { CoreBusinessLegacyIssueVehicleChecklistView } from './CoreBusinessLegacyIssueVehicleChecklistView';

const stableToast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}));

const testMocks = vi.hoisted(() => ({
  fetchModules: vi.fn(),
  fetchVehicles: vi.fn(),
  routeParams: {
    vehicleModelId: 'vehicle-a',
    workspaceSlug: 'research',
  },
  searchParams: new URLSearchParams('stage_id=stage-a-p1'),
  setSearchParams: vi.fn(
    (
      next: URLSearchParams | ((current: URLSearchParams) => URLSearchParams),
    ) => {
      testMocks.searchParams =
        typeof next === 'function' ? next(testMocks.searchParams) : next;
    },
  ),
  translate: vi.fn((key: string) => {
    const labels: Record<string, string> = {
      'nav.legacy-issues-aircon': 'Air Conditioner',
      'nav.legacy-issues-compressor-mechanical': 'Mechanical',
      'nav.legacy-issues-heat-exchanger': 'Heat Exchanger',
      'nav.legacy-issues-interior': 'Interior',
      'categories.legacy-issues-compressor': 'Compressor',
      'coreBusiness.vehicleChecklist.summaryRevision': 'Master Rev. 17',
    };
    return labels[key] ?? key;
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US' },
    t: testMocks.translate,
  }),
}));

vi.mock('@open-alm/ui', () => ({
  useToast: () => stableToast,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token' }),
}));

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) =>
    createElement('a', { href: to }, children),
  useParams: () => testMocks.routeParams,
  useSearchParams: () => [testMocks.searchParams, testMocks.setSearchParams],
}));

vi.mock('../api/legacy-issue-vehicle-api', () => ({
  fetchLegacyIssueVehicleChecklistModules: testMocks.fetchModules,
  fetchLegacyIssueVehicleModels: testMocks.fetchVehicles,
}));

beforeEach(() => {
  vi.clearAllMocks();
  testMocks.routeParams.vehicleModelId = 'vehicle-a';
  testMocks.routeParams.workspaceSlug = 'research';
  testMocks.searchParams = new URLSearchParams('stage_id=stage-a-p1');
  testMocks.fetchVehicles.mockResolvedValue({
    items: [
      {
        active: true,
        checklist_summary: null,
        created_at: '2026-07-15T00:00:00Z',
        id: 'vehicle-a',
        notes: null,
        stages: [
          stage('stage-a-p0', 'vehicle-a', 'P0', 1),
          stage('stage-a-p1', 'vehicle-a', 'P1', 2, 'stage-a-p0'),
        ],
        updated_at: '2026-07-15T00:00:00Z',
        vehicle_code: 'MX5',
        vehicle_name: 'Santa Fe',
      },
      {
        active: true,
        checklist_summary: null,
        created_at: '2026-07-15T00:00:00Z',
        id: 'vehicle-b',
        notes: null,
        stages: [stage('stage-b-p0', 'vehicle-b', 'P0', 1)],
        updated_at: '2026-07-15T00:00:00Z',
        vehicle_code: 'NX4',
        vehicle_name: 'Tucson',
      },
    ],
  });
});

afterEach(cleanup);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function moduleResponse(
  moduleKey: string,
  checklistId: string,
  stageId = 'stage-a-p1',
) {
  return {
    items: [
      {
        checklist_count: 1,
        latest_checklist: {
          completed_at: null,
          completed_by_id: null,
          created_at: '2026-07-15T00:00:00Z',
          created_by_id: 'user-1',
          id: checklistId,
          module_key: moduleKey,
          row_count: 12,
          source_dataset_key: 'common-master',
          source_master_revision_id: 'master-17',
          source_master_revision_no: 17,
          stage_id: stageId,
          seeded_from_checklist_id: null,
          status: 'draft',
          updated_at: '2026-07-15T00:00:00Z',
          vehicle_model_id: moduleKey === 'aircon' ? 'vehicle-a' : 'vehicle-b',
        },
        latest_master_revision: { id: 'master-17', revision_no: 17 },
        module_key: moduleKey,
      },
    ],
  };
}

describe('module-based vehicle checklist navigation', () => {
  it('provides the module flow and permanent-delete copy in both locales', () => {
    for (const locale of ['ko-KR', 'en-US'] as const) {
      const copy = resources[locale].apps.coreBusiness.vehicleChecklist;
      expect(copy.actions.backToModules).toBeTruthy();
      expect(copy.actions.backToVehicles).toBeTruthy();
      expect(copy.actions.createChecklist).toBeTruthy();
      expect(copy.confirmDelete.moduleDescription).toContain('{{module}}');
      expect(copy.confirmDelete.moduleDescription).toContain('{{rowCount}}');
      expect(copy.modules.empty).toBeTruthy();
    }
  });

  it('shows the selected vehicle module list and links to its module detail', async () => {
    testMocks.fetchModules.mockResolvedValue(
      moduleResponse('aircon', 'checklist-a'),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleChecklistView));

    const moduleLink = await screen.findByRole('link', {
      name: /Air Conditioner/,
    });
    expect(moduleLink.getAttribute('href')).toBe(
      '/w/research/legacy-issues/vehicle-checklists/vehicle-a/aircon?stage_id=stage-a-p1',
    );
    expect(
      screen.getByRole('link', { name: 'Master Rev. 17' }).getAttribute('href'),
    ).toBe(
      '/w/research/legacy-issues/vehicle-checklists/vehicle-a/aircon?stage_id=stage-a-p1&checklist_id=checklist-a',
    );
    expect(screen.queryByText('MX5 · Santa Fe')).not.toBeNull();
  });

  it('links the heat exchanger module to its checklist detail', async () => {
    testMocks.fetchModules.mockResolvedValue(
      moduleResponse('heat-exchanger', 'checklist-heat-exchanger'),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleChecklistView));

    expect(
      (
        await screen.findByRole('link', {
          name: /Heat Exchanger/,
        })
      ).getAttribute('href'),
    ).toBe(
      '/w/research/legacy-issues/vehicle-checklists/vehicle-a/heat-exchanger?stage_id=stage-a-p1',
    );
  });

  it('shows a module parent category in the module label', async () => {
    testMocks.fetchModules.mockResolvedValue(
      moduleResponse('compressor-mechanical', 'checklist-compressor'),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleChecklistView));

    expect(
      (
        await screen.findByRole('link', {
          name: /Compressor \/ Mechanical/,
        })
      ).getAttribute('href'),
    ).toBe(
      '/w/research/legacy-issues/vehicle-checklists/vehicle-a/compressor-mechanical?stage_id=stage-a-p1',
    );
  });

  it('defaults to the latest registered stage and renders stage tabs', async () => {
    testMocks.searchParams = new URLSearchParams();
    testMocks.fetchModules.mockResolvedValue(
      moduleResponse('aircon', 'checklist-a'),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleChecklistView));

    expect(await screen.findByRole('tab', { name: 'P0' })).not.toBeNull();
    expect(screen.getByRole('tab', { name: 'P1' })).not.toBeNull();
    await waitFor(() =>
      expect(testMocks.setSearchParams).toHaveBeenCalledWith(
        expect.objectContaining({}),
        { replace: true },
      ),
    );
    const normalized = testMocks.setSearchParams.mock.calls.at(-1)?.[0] as
      | URLSearchParams
      | undefined;
    expect(normalized?.get('stage_id')).toBe('stage-a-p1');
    expect(testMocks.fetchModules).toHaveBeenCalledWith(
      expect.objectContaining({ stageId: 'stage-a-p1' }),
    );
  });

  it('loads module summaries for the selected stage', async () => {
    testMocks.searchParams = new URLSearchParams('stage_id=stage-a-p0');
    testMocks.fetchModules.mockResolvedValue(
      moduleResponse('aircon', 'checklist-p0', 'stage-a-p0'),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleChecklistView));

    expect(
      (await screen.findByRole('tab', { name: 'P0' })).getAttribute(
        'aria-selected',
      ),
    ).toBe('true');
    expect(testMocks.fetchModules).toHaveBeenCalledWith({
      stageId: 'stage-a-p0',
      token: 'token',
      vehicleModelId: 'vehicle-a',
      workspaceSlug: 'research',
    });
  });

  it('ignores a delayed module response after navigating to another vehicle', async () => {
    const vehicleA = deferred<ReturnType<typeof moduleResponse>>();
    const vehicleB = deferred<ReturnType<typeof moduleResponse>>();
    testMocks.fetchModules.mockImplementation(
      ({ vehicleModelId }: { vehicleModelId: string }) =>
        vehicleModelId === 'vehicle-a' ? vehicleA.promise : vehicleB.promise,
    );

    const rendered = render(
      createElement(CoreBusinessLegacyIssueVehicleChecklistView),
    );
    await waitFor(() =>
      expect(testMocks.fetchModules).toHaveBeenCalledWith(
        expect.objectContaining({ vehicleModelId: 'vehicle-a' }),
      ),
    );

    testMocks.routeParams.vehicleModelId = 'vehicle-b';
    testMocks.searchParams = new URLSearchParams('stage_id=stage-b-p0');
    rendered.rerender(
      createElement(CoreBusinessLegacyIssueVehicleChecklistView),
    );
    await waitFor(() =>
      expect(testMocks.fetchModules).toHaveBeenCalledWith(
        expect.objectContaining({ vehicleModelId: 'vehicle-b' }),
      ),
    );

    await act(async () => {
      vehicleB.resolve(moduleResponse('interior', 'checklist-b', 'stage-b-p0'));
    });
    expect(
      await screen.findByRole('link', { name: /Interior/ }),
    ).not.toBeNull();

    await act(async () => {
      vehicleA.resolve(moduleResponse('aircon', 'checklist-a'));
    });
    expect(screen.queryByRole('link', { name: /Air Conditioner/ })).toBeNull();
    expect(screen.queryByText('NX4 · Tucson')).not.toBeNull();
  });
});

function stage(
  id: string,
  vehicleModelId: string,
  name: string,
  sequenceNo: number,
  previousStageId: string | null = null,
) {
  return {
    created_at: '2026-07-15T00:00:00Z',
    id,
    name,
    previous_stage_id: previousStageId,
    sequence_no: sequenceNo,
    updated_at: '2026-07-15T00:00:00Z',
    vehicle_model_id: vehicleModelId,
  };
}
