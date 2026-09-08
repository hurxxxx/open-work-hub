import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PmsSpace, PmsTaskList } from '../api/pms-api';
import { SpaceOverviewView } from '../views/SpaceOverviewView';
import { resolvePmsViewRoute } from '../views/pms-view-route';
import { PmsSidebarSpaces } from './PmsSidebarSpaces';

const mocks = vi.hoisted(() => ({
  createSpace: vi.fn(),
  createPmsTaskList: vi.fn(),
  listSpaces: vi.fn(),
  listPmsTaskLists: vi.fn(),
  listAllPmsTaskLists: vi.fn(),
  listFolders: vi.fn(),
  listSpaceMembers: vi.fn(),
  listPmsUsers: vi.fn(),
  listDocsHub: vi.fn(),
  feedback: vi.fn(),
  translate: (key: string) => key,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US', resolvedLanguage: 'en-US' },
    t: mocks.translate,
  }),
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-token', user: { id: 'owner' } }),
}));
vi.mock('@/src/platform/apps/app-bootstrap-context', () => ({
  useAppAdmission: () => true,
}));
vi.mock('@open-work-hub/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => mocks.feedback,
}));
vi.mock('@open-work-hub/ui/feedback/confirm-dialog', () => ({
  useConfirm: () => ({ confirm: vi.fn(), confirmDialog: null }),
}));
vi.mock('@open-work-hub/ui/feedback/prompt-dialog', () => ({
  usePrompt: () => ({ prompt: vi.fn(), promptDialog: null }),
}));
vi.mock('@/src/app-modules/docs/public-api', () => ({
  listDocsHub: mocks.listDocsHub,
}));
vi.mock('../api/pms-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/pms-api')>()),
  createSpace: mocks.createSpace,
  createPmsTaskList: mocks.createPmsTaskList,
  listSpaces: mocks.listSpaces,
  listPmsTaskLists: mocks.listPmsTaskLists,
  listAllPmsTaskLists: mocks.listAllPmsTaskLists,
  listFolders: mocks.listFolders,
  listSpaceMembers: mocks.listSpaceMembers,
  listPmsUsers: mocks.listPmsUsers,
}));
vi.mock('../views/SpaceMembersModal', () => ({
  SpaceMembersModal: () => null,
}));
vi.mock('./SpaceOrderEditorModal', () => ({
  SpaceOrderEditorModal: () => null,
}));

const alpha: PmsSpace = {
  id: 'space-alpha',
  key: 'alpha',
  name: 'Alpha',
  description: '',
  member_count: 1,
  current_user_role: 'owner',
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
};
const beta: PmsSpace = {
  ...alpha,
  id: 'space-beta',
  key: 'beta',
  name: 'Beta',
};
const betaList: PmsTaskList = {
  id: 'list-beta',
  key: 'beta-list',
  name: 'Beta delivery',
  description: '',
  status: 'active',
  status_mode: 'inherit',
  archived: false,
  team_id: beta.id,
  team_name: beta.name,
  folder_id: null,
  folder_name: null,
  sort_order: 0,
  role: 'owner',
  progress: 0,
  member_count: 1,
  milestone_count: 0,
  task_count: 0,
  overdue_task_count: 0,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
};

function PmsNavigationHarness() {
  const { pathname } = useLocation();
  const route = resolvePmsViewRoute({
    createTaskRequested: false,
    isNewTaskModalOpen: false,
    routePathname: pathname,
  });
  return (
    <>
      <output aria-label="Current route">{pathname}</output>
      <PmsSidebarSpaces
        activeNavItemId={
          route.kind === 'spaceOverview' ? `space:${route.spaceId}` : ''
        }
        isExpanded
        onToggle={() => undefined}
      />
      {route.kind === 'spaceOverview' ? (
        <SpaceOverviewView spaceId={route.spaceId} />
      ) : null}
    </>
  );
}

function renderAlpha() {
  return render(
    <MemoryRouter initialEntries={['/apps/pms/spaces/space-alpha']}>
      <PmsNavigationHarness />
    </MemoryRouter>,
  );
}

async function submitBeta() {
  await screen.findByRole('heading', { name: 'Alpha', level: 1 });
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', { name: 'pms.sidebar.newSpace' }),
    );
  });
  fireEvent.change(
    screen.getByLabelText('apps:pms.spaceName', { exact: false }),
    {
      target: { value: 'Beta' },
    },
  );
  await act(async () => {
    fireEvent.click(
      screen.getByRole('button', { name: 'apps:pms.createSpace' }),
    );
  });
}

describe('PMS sidebar space creation navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listSpaces.mockResolvedValue([alpha]);
    mocks.listPmsTaskLists.mockResolvedValue({ items: [], total: 0 });
    mocks.listAllPmsTaskLists.mockResolvedValue({ items: [], total: 0 });
    mocks.listFolders.mockResolvedValue({ items: [] });
    mocks.listSpaceMembers.mockResolvedValue({ items: [] });
    mocks.listPmsUsers.mockResolvedValue([]);
    mocks.listDocsHub.mockResolvedValue({ items: [] });
    mocks.createSpace.mockImplementation(async () => {
      mocks.listSpaces.mockResolvedValue([alpha, beta]);
      return beta;
    });
    mocks.createPmsTaskList.mockResolvedValue(betaList);
  });

  it('opens the created space and targets its id when creating a list from the overview', async () => {
    renderAlpha();
    await submitBeta();

    await waitFor(() => {
      expect(screen.getByLabelText('Current route').textContent).toBe(
        '/apps/pms/spaces/space-beta',
      );
    });
    await screen.findByRole('heading', { name: 'Beta', level: 1 });
    expect(
      screen.queryByRole('heading', { name: 'Alpha', level: 1 }),
    ).toBeNull();
    expect(mocks.listPmsTaskLists).toHaveBeenCalledWith('test-token', beta.id);

    fireEvent.click(
      screen.getAllByRole('button', { name: 'pms.spaceOverview.newList' })[0],
    );
    fireEvent.change(screen.getByLabelText('apps:pms.name', { exact: false }), {
      target: { value: betaList.name },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'apps:pms.create' }));
    });

    await waitFor(() => {
      expect(mocks.createPmsTaskList).toHaveBeenCalledWith(
        'test-token',
        expect.objectContaining({ name: betaList.name, team_id: beta.id }),
      );
      expect(screen.getByLabelText('Current route').textContent).toBe(
        '/apps/pms/lists/list-beta',
      );
    });
  });

  it('keeps the current space and the failure visible when creation is rejected', async () => {
    mocks.createSpace.mockRejectedValue(new Error('Space creation rejected'));
    renderAlpha();
    await submitBeta();

    await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain(
      'Space creation rejected',
    );
    expect(screen.getByLabelText('Current route').textContent).toBe(
      '/apps/pms/spaces/space-alpha',
    );
    expect(mocks.listPmsTaskLists).not.toHaveBeenCalledWith(
      'test-token',
      beta.id,
    );
    expect(mocks.createPmsTaskList).not.toHaveBeenCalled();
  });
});
