import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { WhiteboardDetail } from '../api/whiteboard-api';
import { WhiteboardEditorSurface } from './WhiteboardEditorSurface';

const state = vi.hoisted(() => ({
  t: (key: string) => key,
  listeners: new Set<(event: { data: unknown }) => void>(),
  subscribe: vi.fn(() => vi.fn()),
  addEventListener: vi.fn(
    (_type: string, listener: (event: { data: unknown }) => void) => {
      state.listeners.add(listener);
      return () => {
        state.listeners.delete(listener);
      };
    },
  ),
  getWhiteboard: vi.fn(),
  getWhiteboardSharing: vi.fn(),
  listWhiteboardShareableUsers: vi.fn(),
  upsertWhiteboardLinkShare: vi.fn(),
  getSharedWhiteboard: vi.fn(),
  recordWhiteboardView: vi.fn(),
  recordSharedWhiteboardView: vi.fn(),
}));
vi.mock('@/src/platform/realtime/realtime-provider', () => ({
  useRealtime: () => state,
}));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: state.t }) }));
vi.mock('../api/whiteboard-api', async (original) => ({
  ...(await original<typeof import('../api/whiteboard-api')>()),
  getWhiteboard: state.getWhiteboard,
  getWhiteboardSharing: state.getWhiteboardSharing,
  listWhiteboardShareableUsers: state.listWhiteboardShareableUsers,
  upsertWhiteboardLinkShare: state.upsertWhiteboardLinkShare,
  getSharedWhiteboard: state.getSharedWhiteboard,
  recordWhiteboardView: state.recordWhiteboardView,
  recordSharedWhiteboardView: state.recordSharedWhiteboardView,
}));
vi.mock('./WhiteboardGroupSharing', () => ({
  WhiteboardGroupSharing: () => null,
}));
vi.mock('@excalidraw/excalidraw', () => ({
  restoreLibraryItems: () => [],
  THEME: { LIGHT: 'light', DARK: 'dark' },
  Excalidraw: ({
    viewModeEnabled,
    initialData,
  }: {
    viewModeEnabled: boolean;
    initialData: { elements: Array<{ id: string }> };
  }) => (
    <div data-testid="canvas" data-readonly={viewModeEnabled}>
      {initialData.elements.map((element) => element.id).join(',')}
    </div>
  ),
}));

function board(canEdit = false): WhiteboardDetail {
  return {
    id: 'board',
    title: 'Protected board',
    can_edit: canEdit,
    can_manage: false,
    can_share: false,
    scene: { elements: [{ id: 'protected-scene' }], appState: {}, files: {} },
    targets: [],
    owner: { id: 'owner', full_name: 'Owner' },
  } as unknown as WhiteboardDetail;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function invalidate() {
  act(() => {
    state.listeners.forEach((listener) =>
      listener({ data: { whiteboard_id: 'board' } }),
    );
  });
}

beforeEach(() => {
  state.listeners.clear();
  vi.clearAllMocks();
});

describe('WhiteboardEditorSurface access invalidation', () => {
  it.each([null, 'share-lens'])(
    'clears a visible board immediately and rechecks its exact access lens (%s)',
    async (shareToken) => {
      const loader = shareToken
        ? state.getSharedWhiteboard
        : state.getWhiteboard;
      const next = deferred<WhiteboardDetail>();
      loader.mockResolvedValueOnce(board()).mockReturnValueOnce(next.promise);
      render(
        <WhiteboardEditorSurface boardId="board" shareToken={shareToken} />,
      );
      await screen.findByTestId('canvas');
      invalidate();
      expect(screen.queryByTestId('canvas')).toBeNull();
      await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
      expect(loader).toHaveBeenLastCalledWith(
        'test-token',
        shareToken ?? 'board',
      );
      expect(state.subscribe).toHaveBeenCalledTimes(1);
      await act(async () => {
        next.resolve(board());
      });
      expect(screen.getByTestId('canvas').textContent).toBe('protected-scene');
    },
  );

  it.each([null, 'share-lens'])(
    'does not restore an old pending result after current access is denied (%s)',
    async (shareToken) => {
      const loader = shareToken
        ? state.getSharedWhiteboard
        : state.getWhiteboard;
      const stale = deferred<WhiteboardDetail>();
      const onBoardLoaded = vi.fn();
      loader
        .mockReturnValueOnce(stale.promise)
        .mockRejectedValueOnce(new Error('Access denied'));
      render(
        <WhiteboardEditorSurface
          boardId="board"
          shareToken={shareToken}
          onBoardLoaded={onBoardLoaded}
        />,
      );
      invalidate();
      await screen.findByText('Access denied');
      await act(async () => {
        stale.resolve(board());
      });
      expect(screen.queryByTestId('canvas')).toBeNull();
      expect(onBoardLoaded).not.toHaveBeenCalled();
      expect(state.recordWhiteboardView).not.toHaveBeenCalled();
      expect(state.recordSharedWhiteboardView).not.toHaveBeenCalled();
    },
  );

  it('applies the current link edit level without inheriting owner/direct rights', async () => {
    state.getSharedWhiteboard
      .mockResolvedValueOnce(board(true))
      .mockResolvedValueOnce(board(false));
    render(<WhiteboardEditorSurface boardId="board" shareToken="share-lens" />);
    expect(
      (await screen.findByTestId('canvas')).getAttribute('data-readonly'),
    ).toBe('false');
    invalidate();
    await waitFor(() =>
      expect(screen.getByTestId('canvas').getAttribute('data-readonly')).toBe(
        'true',
      ),
    );
    expect(state.getWhiteboard).not.toHaveBeenCalled();
  });
  it('rotates the current link explicitly without upgrading its access level', async () => {
    state.getWhiteboard.mockResolvedValue({ ...board(), can_share: true });
    const sharing = {
      whiteboard_id: 'board',
      owner_id: 'owner',
      users: [],
      link_share: {
        token: 'old-test-link',
        access_level: 'read',
        active: true,
        share_path: '/apps/whiteboard/shared/old-test-link',
      },
    };
    state.getWhiteboardSharing.mockResolvedValue(sharing);
    state.listWhiteboardShareableUsers.mockResolvedValue([]);
    state.upsertWhiteboardLinkShare.mockResolvedValue({
      ...sharing,
      link_share: {
        ...sharing.link_share,
        token: 'new-test-link',
        share_path: '/apps/whiteboard/shared/new-test-link',
      },
    });
    render(<WhiteboardEditorSurface boardId="board" />);
    fireEvent.click(
      await screen.findByRole('button', { name: 'common:actions.share' }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'docs.share.regenerate' }),
    );
    await waitFor(() =>
      expect(state.upsertWhiteboardLinkShare).toHaveBeenCalledWith(
        'test-token',
        'board',
        { access_level: 'read', regenerate_token: true },
      ),
    );
    await waitFor(() =>
      expect(
        (screen.getByLabelText('whiteboard.shareLinkUrl') as HTMLInputElement)
          .value,
      ).toContain('/new-test-link'),
    );
  });
});
