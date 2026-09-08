import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useEffect } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { REALTIME_TOPIC_EVENT_TYPES } from '@open-work-hub/contracts/realtime';
import {
  DocsApiError,
  getDocsItem,
  listDocPages,
  updateDocPage,
  type DocsHubItem,
  type DocsPageItem,
} from '../api/docs-api';
import { DocsEmbeddedViewer } from './DocsViewerModal';
import { DocsHtmlRenderPage } from './DocsHtmlRenderPage';

const state = vi.hoisted(() => ({
  listeners: new Map<string, (event: { data: { doc_id: string } }) => void>(),
  t: (key: string) => key,
  media: { uploadFile: vi.fn(), resolveFileUrl: vi.fn() },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: state.t }) }));
vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'session-1' }),
}));
vi.mock('@/src/platform/media/use-media-upload', () => ({
  useMediaUpload: () => state.media,
}));
vi.mock('@/src/platform/realtime/realtime-provider', () => ({
  useRealtime: () => ({ reconnectSeq: 1 }),
  useRealtimeSubscription: vi.fn(),
  useRealtimeEvent: (
    type: string,
    listener: (event: { data: { doc_id: string } }) => void,
  ) => {
    useEffect(() => {
      state.listeners.set(type, listener);
      return () => {
        state.listeners.delete(type);
      };
    }, [type, listener]);
  },
}));
vi.mock('@open-work-hub/ui', async (original) => ({
  ...(await original<typeof import('@open-work-hub/ui')>()),
  useConfirm: () => ({ confirm: vi.fn(), confirmDialog: null }),
}));
vi.mock('../api/docs-api', async (original) => ({
  ...(await original<typeof import('../api/docs-api')>()),
  getDocsItem: vi.fn(),
  listDocPages: vi.fn(),
  updateDocPage: vi.fn(),
  recordDocView: vi.fn(),
}));
vi.mock('./DocsBlockContentSurface', () => ({
  DocsBlockContentSurface: () => null,
}));
vi.mock('./docs-html-renderers', () => ({
  DocsHtmlFrame: ({ content }: { content: string }) => <div>{content}</div>,
  DocsHtmlPageContentSurface: ({
    canEdit,
    content,
    onChange,
  }: {
    canEdit: boolean;
    content: string;
    onChange: (value: string) => void;
  }) => (
    <div>
      <p>{content}</p>
      {canEdit ? (
        <textarea
          aria-label="HTML source"
          value={content}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : null}
    </div>
  ),
}));

const doc = {
  id: 'doc-1',
  title: 'Private HTML',
  content_format: 'html',
  can_edit: true,
} as DocsHubItem;
const docPage = {
  id: 'page-1',
  title: 'Private page',
  content_format: 'html',
  content_text: 'Private body',
  parent_id: null,
  sort_order: 0,
  can_edit: true,
} as DocsPageItem;
const pages = { items: [docPage] };

function notifyAccess(docId = 'doc-1') {
  act(() => {
    state.listeners.get(REALTIME_TOPIC_EVENT_TYPES.docsAccessChanged)?.({
      data: { doc_id: docId },
    });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  state.listeners.clear();
  vi.mocked(getDocsItem).mockResolvedValue(doc);
  vi.mocked(listDocPages).mockResolvedValue(pages);
});

describe('Docs access changes in secondary views', () => {
  it('reloads embedded authority, drops queued text on downgrade, and ignores a late revoked response', async () => {
    render(<DocsEmbeddedViewer itemId="doc-1" />);
    await screen.findByText('Private body', { selector: 'p' });
    await waitFor(() => expect(listDocPages).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByRole('textbox', { name: 'HTML source' }), {
      target: { value: 'Unsaved private draft' },
    });
    vi.mocked(getDocsItem).mockResolvedValue({ ...doc, can_edit: false });
    notifyAccess();
    await screen.findByText('Private body', { selector: 'p' });
    expect(screen.queryByRole('textbox', { name: 'HTML source' })).toBeNull();
    expect(updateDocPage).not.toHaveBeenCalled();
    await waitFor(() => expect(listDocPages).toHaveBeenCalledTimes(4));

    let releaseOld!: (result: typeof pages) => void;
    vi.mocked(listDocPages).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseOld = resolve;
        }),
    );
    act(() => {
      state.listeners.get(REALTIME_TOPIC_EVENT_TYPES.docsPagesChanged)?.({
        data: { doc_id: 'doc-1' },
      });
    });
    await waitFor(() => expect(releaseOld).toBeTypeOf('function'));
    vi.mocked(getDocsItem).mockRejectedValue(new DocsApiError(404, 'Revoked'));
    vi.mocked(listDocPages).mockRejectedValue(new DocsApiError(404, 'Revoked'));
    notifyAccess();
    await screen.findByText('apps:docs.viewer.loadFailed');
    expect(screen.queryByText('Private body', { selector: 'p' })).toBeNull();
    await act(async () => {
      releaseOld(pages);
    });
    expect(screen.queryByText('Private body', { selector: 'p' })).toBeNull();
    expect(updateDocPage).not.toHaveBeenCalled();
  });

  it('clears embedded pages when a normal content refresh returns denied', async () => {
    render(<DocsEmbeddedViewer itemId="doc-1" />);
    await screen.findByText('Private body', { selector: 'p' });
    await waitFor(() => expect(listDocPages).toHaveBeenCalledTimes(2));
    vi.mocked(listDocPages).mockRejectedValue(new DocsApiError(403, 'Revoked'));
    act(() => {
      state.listeners.get(REALTIME_TOPIC_EVENT_TYPES.docsPagesChanged)?.({
        data: { doc_id: 'doc-1' },
      });
    });
    await screen.findByText('apps:docs.viewer.loadFailed');
    expect(screen.queryByText('Private body', { selector: 'p' })).toBeNull();
  });

  it('removes standalone HTML immediately and ignores late responses from an earlier authority decision', async () => {
    render(
      <MemoryRouter initialEntries={['/documents/doc-1/pages/page-1']}>
        <Routes>
          <Route
            path="/documents/:docId/pages/:pageId"
            element={<DocsHtmlRenderPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText('Private body');
    notifyAccess('unrelated-doc');
    expect(getDocsItem).toHaveBeenCalledTimes(1);
    let releaseOld!: (result: typeof pages) => void;
    vi.mocked(listDocPages).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseOld = resolve;
        }),
    );
    notifyAccess();
    await waitFor(() => expect(releaseOld).toBeTypeOf('function'));
    expect(screen.queryByText('Private body')).toBeNull();
    vi.mocked(getDocsItem).mockRejectedValue(new DocsApiError(404, 'Revoked'));
    vi.mocked(listDocPages).mockRejectedValue(new DocsApiError(404, 'Revoked'));
    notifyAccess();
    await screen.findByText('apps:docs.viewer.loadFailed');
    await act(async () => {
      releaseOld(pages);
    });
    expect(screen.queryByText('Private body')).toBeNull();
  });
});
