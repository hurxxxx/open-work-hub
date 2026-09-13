import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HermesWorkspacePanel } from './HermesWorkspacePanel';

const mocks = vi.hoisted(() => ({
  listFiles: vi.fn(),
  listRuns: vi.fn(),
  listSessions: vi.fn(),
  stop: vi.fn(),
  legacy: vi.fn(),
  legacyFiles: vi.fn(),
  upload: vi.fn(),
  create: vi.fn(),
  feedback: { error: vi.fn(), success: vi.fn() },
  t: (key: string) => key,
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: mocks.t }) }));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));
vi.mock('@open-work-hub/ui', () => ({ useFeedback: () => mocks.feedback }));
vi.mock('../api/hermes-agent-api', () => ({
  listHermesFiles: mocks.listFiles,
  listHermesRuns: mocks.listRuns,
  listHermesSessions: mocks.listSessions,
  stopHermesRun: mocks.stop,
  uploadHermesFile: mocks.upload,
  createHermesSession: mocks.create,
}));
vi.mock('@/src/app-modules/hermes-terminal/public-api', () => ({
  listHermesTerminalSessions: mocks.legacy,
  listHermesTerminalFiles: mocks.legacyFiles,
  downloadHermesTerminalFile: vi.fn(),
}));

const panel = (conversationId: string | null) => (
  <MemoryRouter>
    <HermesWorkspacePanel conversationId={conversationId} />
  </MemoryRouter>
);
const file = (name: string) => ({
  id: name,
  relative_path: name,
  size_bytes: 10,
});

describe('Hermes work and files panel', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.listFiles.mockResolvedValue({ data: [] });
    mocks.listRuns.mockResolvedValue({ data: [] });
    mocks.listSessions.mockResolvedValue({ data: [] });
    mocks.legacy.mockResolvedValue({ items: [] });
    mocks.stop.mockResolvedValue({});
  });
  afterEach(cleanup);

  it('stops the selected run and locks uploads only for the active conversation', async () => {
    mocks.listRuns.mockResolvedValue({
      data: [
        {
          id: 'run-a',
          session_binding_id: 'a',
          status: 'running',
          progress_percent: 10,
        },
        {
          id: 'run-job',
          session_binding_id: null,
          status: 'running',
          progress_percent: 20,
        },
      ],
    });
    const view = render(panel('a'));
    await waitFor(() =>
      expect(screen.getAllByText('hermesWorkspace.stop')).toHaveLength(2),
    );
    expect(
      (screen.getByLabelText('hermesWorkspace.attach') as HTMLInputElement)
        .disabled,
    ).toBe(true);
    fireEvent.click(screen.getAllByText('hermesWorkspace.stop')[0]);
    await waitFor(() =>
      expect(mocks.stop).toHaveBeenCalledWith('test-token', 'run-a'),
    );
    view.rerender(panel(null));
    await waitFor(() =>
      expect(
        (screen.getByLabelText('hermesWorkspace.attach') as HTMLInputElement)
          .disabled,
      ).toBe(false),
    );
  });

  it('discards an old conversation response after navigation', async () => {
    let resolveOld!: (value: { data: ReturnType<typeof file>[] }) => void;
    mocks.listFiles.mockImplementation((_token, id) =>
      id === 'a'
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : Promise.resolve({ data: [file('current.txt')] }),
    );
    const view = render(panel('a'));
    view.rerender(panel('b'));
    await screen.findByText('current.txt');
    await act(async () => resolveOld({ data: [file('stale.txt')] }));
    expect(screen.queryByText('stale.txt')).toBeNull();
    expect(screen.getByText('current.txt')).toBeTruthy();
  });

  it('shows unavailable files and archives without a misleading empty state', async () => {
    mocks.listFiles.mockRejectedValue(new Error('offline'));
    mocks.legacy.mockRejectedValue(new Error('offline'));
    render(panel('a'));
    await screen.findByText('hermesWorkspace.loadFailed');
    await screen.findByText('hermesWorkspace.legacyLoadFailed');
    expect(screen.queryByText('hermesWorkspace.noFiles')).toBeNull();
    expect(
      (screen.getByLabelText('hermesWorkspace.attach') as HTMLInputElement)
        .disabled,
    ).toBe(true);
  });
});
