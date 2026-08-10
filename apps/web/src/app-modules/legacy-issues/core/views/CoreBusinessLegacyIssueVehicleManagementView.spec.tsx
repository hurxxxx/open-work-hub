import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resources } from '@/src/platform/i18n/resources';
import { CoreBusinessLegacyIssueVehicleManagementView } from './CoreBusinessLegacyIssueVehicleManagementView';

const stableToast = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}));

const testMocks = vi.hoisted(() => ({
  canManage: true,
  confirm: vi.fn(),
  createStage: vi.fn(),
  createVehicle: vi.fn(),
  deactivateVehicle: vi.fn(),
  fetchVehicles: vi.fn(),
  permanentDeleteVehicle: vi.fn(),
  updateStage: vi.fn(),
  updateVehicle: vi.fn(),
  translate: vi.fn((key: string, options?: Record<string, unknown>) => {
    const labels: Record<string, string> = {
      'common:actions.cancel': 'Cancel',
      'common:feedback.loading': 'Loading',
      'coreBusiness.vehicleManagement.actions.create': 'Create',
      'coreBusiness.vehicleManagement.actions.activate': 'Activate',
      'coreBusiness.vehicleManagement.actions.deactivate': 'Deactivate',
      'coreBusiness.vehicleManagement.actions.manageStages': 'Add stage',
      'coreBusiness.vehicleManagement.actions.permanentDelete':
        'Delete permanently',
      'coreBusiness.vehicleManagement.actions.reload': 'Refresh',
      'coreBusiness.vehicleManagement.actions.save': 'Save',
      'coreBusiness.vehicleManagement.columns.actions': 'Actions',
      'coreBusiness.vehicleManagement.columns.notes': 'Notes',
      'coreBusiness.vehicleManagement.columns.stages': 'Stages',
      'coreBusiness.vehicleManagement.columns.status': 'Status',
      'coreBusiness.vehicleManagement.columns.updatedAt': 'Updated at',
      'coreBusiness.vehicleManagement.columns.vehicleCode': 'Vehicle code',
      'coreBusiness.vehicleManagement.columns.vehicleName': 'Vehicle name',
      'coreBusiness.vehicleManagement.confirmPermanentDelete.confirm':
        'Delete permanently',
      'coreBusiness.vehicleManagement.confirmPermanentDelete.description':
        'Permanently delete {{vehicle}}. This action cannot be undone.',
      'coreBusiness.vehicleManagement.confirmPermanentDelete.title':
        'Permanently delete this vehicle model?',
      'coreBusiness.vehicleManagement.eyebrow': 'Settings',
      'coreBusiness.vehicleManagement.empty': 'No vehicle models.',
      'coreBusiness.vehicleManagement.errors.manageRequired':
        'Only administrators can manage vehicle models.',
      'coreBusiness.vehicleManagement.form.notes': 'Notes',
      'coreBusiness.vehicleManagement.form.notesPlaceholder': 'Notes',
      'coreBusiness.vehicleManagement.form.vehicleCode': 'Vehicle code',
      'coreBusiness.vehicleManagement.form.vehicleCodePlaceholder':
        'Vehicle code',
      'coreBusiness.vehicleManagement.form.vehicleName': 'Vehicle name',
      'coreBusiness.vehicleManagement.form.vehicleNamePlaceholder':
        'Vehicle name',
      'coreBusiness.vehicleManagement.form.initialStage': 'Initial stage',
      'coreBusiness.vehicleManagement.form.initialStagePlaceholder': 'P0',
      'coreBusiness.vehicleManagement.permanentDeleteBlocked':
        'Cannot delete: {{count}} generated checklists exist.',
      'coreBusiness.vehicleManagement.status.active': 'Active',
      'coreBusiness.vehicleManagement.status.inactive': 'Inactive',
      'coreBusiness.vehicleManagement.status.permanentlyDeleted':
        'Vehicle model permanently deleted.',
      'coreBusiness.vehicleManagement.status.stageCreated':
        'Added the {{name}} stage.',
      'coreBusiness.vehicleManagement.status.stageRenamed':
        'Renamed the stage to {{name}}.',
      'coreBusiness.vehicleManagement.stageDialog.add': 'Add stage',
      'coreBusiness.vehicleManagement.stageDialog.currentStages':
        'Registered stages',
      'coreBusiness.vehicleManagement.stageDialog.description':
        'The stage is added without copying checklists.',
      'coreBusiness.vehicleManagement.stageDialog.duplicateStage':
        'This stage is already registered.',
      'coreBusiness.vehicleManagement.stageDialog.editStageLabel':
        '{{name}} stage name',
      'coreBusiness.vehicleManagement.stageDialog.saveName': 'Save name',
      'coreBusiness.vehicleManagement.stageDialog.stageName': 'New stage',
      'coreBusiness.vehicleManagement.stageDialog.stageNamePlaceholder': 'P1',
      'coreBusiness.vehicleManagement.stageDialog.title':
        'Add stage for {{vehicle}}',
      'coreBusiness.vehicleManagement.summary': '{{active}} / {{total}}',
      'coreBusiness.vehicleManagement.title': 'Vehicle Management',
    };
    return Object.entries(options ?? {}).reduce(
      (value, [name, replacement]) =>
        value.replaceAll(`{{${name}}}`, String(replacement)),
      labels[key] ?? key,
    );
  }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: testMocks.translate }),
}));

vi.mock('@ai-do/ui', () => ({
  Dialog: ({
    actions,
    children,
    open,
    title,
  }: {
    actions?: ReactNode;
    children: ReactNode;
    open: boolean;
    title: ReactNode;
  }) =>
    open ? (
      <div role="dialog" aria-label={String(title)}>
        {children}
        {actions}
      </div>
    ) : null,
  useConfirm: () => ({
    confirm: testMocks.confirm,
    confirmDialog: null,
  }),
  useToast: () => stableToast,
}));

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <span>{value}</span>,
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: { id: 'user-1' } }),
}));

vi.mock('@/src/platform/auth/auth-api', () => ({
  hasWorkspaceAdminAccess: () => testMocks.canManage,
}));

vi.mock('react-router-dom', () => ({
  useParams: () => ({ workspaceSlug: 'research' }),
}));

vi.mock('../api/legacy-issue-vehicle-api', () => ({
  createLegacyIssueVehicleModel: testMocks.createVehicle,
  createLegacyIssueVehicleStage: testMocks.createStage,
  deleteLegacyIssueVehicleModel: testMocks.deactivateVehicle,
  fetchLegacyIssueVehicleModels: testMocks.fetchVehicles,
  permanentlyDeleteLegacyIssueVehicleModel: testMocks.permanentDeleteVehicle,
  updateLegacyIssueVehicleModel: testMocks.updateVehicle,
  updateLegacyIssueVehicleStage: testMocks.updateStage,
}));

beforeEach(() => {
  vi.clearAllMocks();
  testMocks.canManage = true;
  testMocks.confirm.mockResolvedValue(true);
  testMocks.createVehicle.mockResolvedValue(undefined);
  testMocks.createStage.mockResolvedValue(undefined);
  testMocks.updateStage.mockResolvedValue(undefined);
  testMocks.permanentDeleteVehicle.mockResolvedValue(undefined);
  testMocks.fetchVehicles.mockResolvedValue({
    items: [
      vehicle('active-free', 'FREE', true, 0),
      vehicle('inactive-free', 'OFF', false, 0),
      vehicle('blocked', 'USED', true, 2),
    ],
  });
});

afterEach(cleanup);

describe('vehicle model permanent deletion', () => {
  it('uses the common loading translation while vehicle models load', () => {
    testMocks.fetchVehicles.mockImplementation(
      () => new Promise(() => undefined),
    );

    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    expect(screen.getByText('Loading')).not.toBeNull();
    expect(testMocks.translate).toHaveBeenCalledWith('common:feedback.loading');
  });

  it('shows the administrator action for active and inactive unused vehicles and deletes after confirmation', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    const activeRow = await vehicleRow('FREE');
    const inactiveRow = await vehicleRow('OFF');
    const activeDelete = within(activeRow).getByRole('button', {
      name: 'Delete permanently',
    });
    const inactiveDelete = within(inactiveRow).getByRole('button', {
      name: 'Delete permanently',
    });
    expect((activeDelete as HTMLButtonElement).disabled).toBe(false);
    expect((inactiveDelete as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(activeDelete);

    await waitFor(() =>
      expect(testMocks.confirm).toHaveBeenCalledWith(
        expect.objectContaining({
          confirmLabel: 'Delete permanently',
          description:
            'Permanently delete FREE · Model FREE. This action cannot be undone.',
          variant: 'danger',
        }),
      ),
    );
    await waitFor(() =>
      expect(testMocks.permanentDeleteVehicle).toHaveBeenCalledWith({
        token: 'token',
        vehicleModelId: 'active-free',
        workspaceSlug: 'research',
      }),
    );
    expect(stableToast.success).toHaveBeenCalledWith(
      'Vehicle model permanently deleted.',
    );
  });

  it('disables permanent deletion and explains the generated checklist dependency', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    const blockedRow = await vehicleRow('USED');
    const deleteButton = within(blockedRow).getByRole('button', {
      name: 'Delete permanently',
    });
    expect((deleteButton as HTMLButtonElement).disabled).toBe(true);
    expect(
      within(blockedRow).getByText(
        'Cannot delete: 2 generated checklists exist.',
      ),
    ).not.toBeNull();
    fireEvent.click(deleteButton);
    expect(testMocks.confirm).not.toHaveBeenCalled();
    expect(testMocks.permanentDeleteVehicle).not.toHaveBeenCalled();
  });

  it('does not delete when the administrator cancels the confirmation', async () => {
    testMocks.confirm.mockResolvedValue(false);
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    const activeRow = await vehicleRow('FREE');
    fireEvent.click(
      within(activeRow).getByRole('button', {
        name: 'Delete permanently',
      }),
    );

    await waitFor(() => expect(testMocks.confirm).toHaveBeenCalledTimes(1));
    expect(testMocks.permanentDeleteVehicle).not.toHaveBeenCalled();
  });

  it('hides permanent deletion from non-administrators', async () => {
    testMocks.canManage = false;
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    await vehicleRow('FREE');
    expect(
      screen.queryByRole('button', { name: 'Delete permanently' }),
    ).toBeNull();
  });

  it('allows non-administrators to create vehicles while keeping management actions disabled', async () => {
    testMocks.canManage = false;
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    fireEvent.change(screen.getByLabelText('Vehicle code'), {
      target: { value: 'NEW-CAR' },
    });
    fireEvent.change(screen.getByLabelText('Vehicle name'), {
      target: { value: 'New model' },
    });
    fireEvent.change(screen.getByLabelText('Notes'), {
      target: { value: 'Created by a member' },
    });
    fireEvent.change(screen.getByLabelText('Initial stage'), {
      target: { value: 'P0' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(testMocks.createVehicle).toHaveBeenCalledWith({
        initialStageName: 'P0',
        notes: 'Created by a member',
        token: 'token',
        vehicleCode: 'NEW-CAR',
        vehicleName: 'New model',
        workspaceSlug: 'research',
      }),
    );

    const row = await vehicleRow('FREE');
    expect(
      (within(row).getByRole('button', { name: 'Save' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (
        within(row).getByRole('button', {
          name: 'Deactivate',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(stableToast.error).not.toHaveBeenCalledWith(
      'Only administrators can manage vehicle models.',
    );
  });

  it('requires an initial stage when a vehicle is created', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    fireEvent.change(screen.getByLabelText('Vehicle code'), {
      target: { value: 'NEW-CAR' },
    });
    const createButton = screen.getByRole('button', { name: 'Create' });
    expect((createButton as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(screen.getByLabelText('Initial stage'), {
      target: { value: 'P0' },
    });
    expect((createButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(createButton);

    await waitFor(() =>
      expect(testMocks.createVehicle).toHaveBeenCalledWith(
        expect.objectContaining({
          initialStageName: 'P0',
          vehicleCode: 'NEW-CAR',
        }),
      ),
    );
  });

  it('shows ordered stage badges and adds the next stage from the action dialog', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    const row = await vehicleRow('FREE');
    const badges = within(row).getAllByText(/^P[01]$/);
    expect(badges.map((badge) => badge.textContent)).toEqual(['P0', 'P1']);

    fireEvent.click(
      within(row).getByRole('button', {
        name: 'Add stage',
      }),
    );
    const dialog = screen.getByRole('dialog');
    fireEvent.change(screen.getByLabelText('New stage'), {
      target: { value: 'P2' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add stage' }));

    await waitFor(() =>
      expect(testMocks.createStage).toHaveBeenCalledWith({
        name: 'P2',
        token: 'token',
        vehicleModelId: 'active-free',
        workspaceSlug: 'research',
      }),
    );
  });

  it('renames an existing stage from the stage dialog', async () => {
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    const row = await vehicleRow('FREE');
    fireEvent.click(within(row).getByRole('button', { name: 'Add stage' }));
    const stageInput = screen.getByLabelText('P0 stage name');
    fireEvent.change(stageInput, { target: { value: 'VP' } });
    const stageRow = stageInput.parentElement;
    if (!stageRow) throw new Error('Stage row not found');
    fireEvent.click(
      within(stageRow).getByRole('button', { name: 'Save name' }),
    );

    await waitFor(() =>
      expect(testMocks.updateStage).toHaveBeenCalledWith({
        name: 'VP',
        stageId: 'active-free-P0',
        token: 'token',
        vehicleModelId: 'active-free',
        workspaceSlug: 'research',
      }),
    );
  });

  it('shows status as text and toggles active state only from the action column', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(createElement(CoreBusinessLegacyIssueVehicleManagementView));

    const activeRow = await vehicleRow('FREE');
    expect(
      within(activeRow).queryByRole('button', { name: 'Active' }),
    ).toBeNull();
    fireEvent.click(
      within(activeRow).getByRole('button', { name: 'Deactivate' }),
    );
    await waitFor(() =>
      expect(testMocks.deactivateVehicle).toHaveBeenCalledWith({
        token: 'token',
        vehicleModelId: 'active-free',
        workspaceSlug: 'research',
      }),
    );

    const inactiveRow = await vehicleRow('OFF');
    expect(
      within(inactiveRow).queryByRole('button', { name: 'Inactive' }),
    ).toBeNull();
    fireEvent.click(
      within(inactiveRow).getByRole('button', { name: 'Activate' }),
    );
    await waitFor(() =>
      expect(testMocks.updateVehicle).toHaveBeenCalledWith({
        active: true,
        token: 'token',
        vehicleModelId: 'inactive-free',
        workspaceSlug: 'research',
      }),
    );
    confirmSpy.mockRestore();
  });

  it('provides permanent-delete copy in both supported locales', () => {
    for (const locale of ['ko-KR', 'en-US'] as const) {
      const copy = resources[locale].apps.coreBusiness.vehicleManagement;
      expect(copy.actions.permanentDelete).toBeTruthy();
      expect(copy.confirmPermanentDelete.description).toContain('{{vehicle}}');
      expect(copy.permanentDeleteBlocked).toContain('{{count}}');
      expect(copy.status.permanentlyDeleted).toBeTruthy();
    }
  });
});

function vehicle(
  id: string,
  code: string,
  active: boolean,
  generatedChecklistCount: number,
) {
  return {
    active,
    checklist_summary: null,
    created_at: '2026-07-15T00:00:00Z',
    generated_checklist_count: generatedChecklistCount,
    id,
    notes: null,
    stages:
      id === 'active-free'
        ? [stage(id, 'P1', 2), stage(id, 'P0', 1)]
        : [stage(id, 'P0', 1)],
    updated_at: '2026-07-15T00:00:00Z',
    vehicle_code: code,
    vehicle_name: `Model ${code}`,
  };
}

function stage(vehicleModelId: string, name: string, sequenceNo: number) {
  return {
    created_at: '2026-07-15T00:00:00Z',
    id: `${vehicleModelId}-${name}`,
    name,
    previous_stage_id: sequenceNo === 1 ? null : `${vehicleModelId}-P0`,
    sequence_no: sequenceNo,
    updated_at: '2026-07-15T00:00:00Z',
    vehicle_model_id: vehicleModelId,
  };
}

async function vehicleRow(code: string): Promise<HTMLTableRowElement> {
  const input = await screen.findByDisplayValue(code);
  const row = input.closest('tr');
  if (!(row instanceof HTMLTableRowElement)) {
    throw new Error(`Vehicle row not found for ${code}`);
  }
  return row;
}
