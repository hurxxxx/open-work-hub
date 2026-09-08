import { act, render, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import {
  listFavoriteDocs,
  listRecentPages,
  type FavoriteDocItem,
} from './api/docs-api';
import { DocsSidebarExtras } from './sidebar';

const state = vi.hoisted(() => ({
  listener: null as null | ((event: { data: { doc_id: string } }) => void),
  t: (key: string) => key,
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: state.t }) }));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'session' }),
}));
vi.mock('@/src/platform/realtime/realtime-provider', () => ({
  useRealtime: () => ({ reconnectSeq: 1 }),
  useRealtimeEvent: (
    _type: string,
    listener: (event: { data: { doc_id: string } }) => void,
  ) => {
    useEffect(() => {
      state.listener = listener;
      return () => {
        state.listener = null;
      };
    }, [listener]);
  },
}));
vi.mock('./api/docs-api', () => ({
  listFavoriteDocs: vi.fn(),
  listRecentPages: vi.fn(),
}));
const favorites = [
  { id: 'doc-1', title: 'Private favorite' },
] as FavoriteDocItem[];
beforeEach(() => {
  vi.clearAllMocks();
  state.listener = null;
  vi.mocked(listFavoriteDocs).mockResolvedValue(favorites);
  vi.mocked(listRecentPages).mockResolvedValue([]);
});

it('invalidates sidebar titles and pending metadata requests when source authority changes', async () => {
  render(
    <MemoryRouter>
      <DocsSidebarExtras />
    </MemoryRouter>,
  );
  await screen.findByText('Private favorite');
  let releaseOld!: (value: FavoriteDocItem[]) => void;
  vi.mocked(listFavoriteDocs).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        releaseOld = resolve;
      }),
  );
  act(() => {
    state.listener?.({ data: { doc_id: 'doc-1' } });
  });
  await waitFor(() => expect(releaseOld).toBeTypeOf('function'));
  expect(screen.queryByText('Private favorite')).toBeNull();
  vi.mocked(listFavoriteDocs).mockResolvedValue([]);
  act(() => {
    state.listener?.({ data: { doc_id: 'doc-1' } });
  });
  await waitFor(() => expect(listFavoriteDocs).toHaveBeenCalledTimes(3));
  await act(async () => {
    releaseOld(favorites);
  });
  expect(screen.queryByText('Private favorite')).toBeNull();
});
