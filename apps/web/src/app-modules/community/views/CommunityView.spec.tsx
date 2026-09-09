import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createCommunityPost,
  deleteCommunityComment,
  deleteCommunityPost,
  getCommunityPost,
  listCommunityChannels,
  listCommunityPosts,
  markCommunityPostRead,
} from '../api/community-api';
import { CommunityView } from './CommunityView';

const realtimeHandlers = vi.hoisted(
  () => new Map<string, (event: unknown) => void>(),
);

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'token', user: null }),
}));

vi.mock('@/src/platform/media/use-media-upload', () => ({
  useMediaUpload: () => ({
    resolveFileUrl: async (url: string) => url,
    uploadFile: async () => 'media:test',
  }),
}));

vi.mock('@/src/platform/realtime/realtime-provider', () => ({
  useRealtimeEvent: (type: string, handler: (event: unknown) => void) => {
    realtimeHandlers.set(type, handler);
  },
}));

vi.mock('@/src/platform/community/CommunityMarkdownEditor', () => ({
  CommunityMarkdownEditor: ({
    ariaLabel,
    onChange,
    value,
  }: {
    ariaLabel: string;
    onChange: (value: string) => void;
    value: string;
  }) => (
    <textarea
      aria-label={ariaLabel}
      onChange={(event) => onChange(event.target.value)}
      value={value}
    />
  ),
  CommunityMarkdownViewer: ({ markdown }: { markdown: string }) => (
    <div>{markdown}</div>
  ),
}));

vi.mock('../api/community-api', () => ({
  createCommunityComment: vi.fn(),
  createCommunityPost: vi.fn(),
  deleteCommunityComment: vi.fn(),
  deleteCommunityPost: vi.fn(),
  getCommunityPost: vi.fn(),
  listCommunityChannels: vi.fn(),
  listCommunityPosts: vi.fn(),
  markCommunityPostRead: vi.fn(),
  resolveCommunityPostMediaUrls: vi.fn(),
  unlockCommunityPost: vi.fn(),
  updateCommunityComment: vi.fn(),
  updateCommunityPost: vi.fn(),
}));

describe('CommunityView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    realtimeHandlers.clear();
    vi.mocked(listCommunityChannels).mockResolvedValue({
      channels: [
        {
          active: true,
          adminOnlyContent: false,
          description: 'General channel',
          forceAnonymous: false,
          id: 'channel-1',
          key: 'general',
          name: 'General',
          position: 1,
          readOnly: false,
          templateBody: '',
          templateTitle: '',
        },
      ],
    });
    vi.mocked(listCommunityPosts).mockResolvedValue({
      page: 1,
      pageSize: 10,
      posts: [],
      total: 0,
    });
    vi.mocked(getCommunityPost).mockResolvedValue({
      authorName: 'Author',
      body: 'Body',
      canModify: true,
      channelKey: 'general',
      commentCount: 0,
      comments: [],
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-1',
      isAnonymous: false,
      isMine: true,
      isRead: false,
      isSecret: false,
      locked: false,
      lockedReason: null,
      title: 'Post title',
      updatedAt: '2026-06-29T00:00:00Z',
    });
    vi.mocked(deleteCommunityPost).mockResolvedValue(undefined);
    vi.mocked(markCommunityPostRead).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('marks an opened post as read without blocking the detail on failure', async () => {
    vi.mocked(markCommunityPostRead).mockRejectedValueOnce(
      new Error('read receipt failed'),
    );

    render(
      <MemoryRouter
        initialEntries={['/apps/community/posts/post-1?channel=general']}
      >
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('heading', { name: 'Post title' }),
    ).toBeTruthy();
    await waitFor(() => {
      expect(markCommunityPostRead).toHaveBeenCalledWith('token', 'post-1');
    });
  });

  it('refreshes an open post when its comment notification arrives', async () => {
    render(
      <MemoryRouter
        initialEntries={['/apps/community/posts/post-1?channel=general']}
      >
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Post title' });
    vi.mocked(getCommunityPost).mockResolvedValue({
      authorName: 'Author',
      body: 'Body',
      canModify: true,
      channelKey: 'general',
      commentCount: 1,
      comments: [
        {
          anonSeq: null,
          authorName: 'Commenter',
          body: 'New realtime comment',
          canModify: false,
          createdAt: '2026-06-29T00:01:00Z',
          id: 'comment-1',
          isAnonymous: false,
          isDeleted: false,
          parentCommentId: null,
          updatedAt: '2026-06-29T00:01:00Z',
        },
      ],
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-1',
      isAnonymous: false,
      isMine: true,
      isRead: true,
      isSecret: false,
      locked: false,
      lockedReason: null,
      title: 'Post title',
      updatedAt: '2026-06-29T00:00:00Z',
    });

    await act(async () => {
      realtimeHandlers.get('notification.created')?.({
        type: 'notification.created',
        data: {
          notification: {
            action_url: '/apps/community/posts/post-1',
            body: 'A new comment was added.',
            created_at: '2026-06-29T00:01:00Z',
            id: 'notification-1',
            is_read: false,
            origin_app_id: 'community',
            source_id: 'post-1',
            source_type: 'community_post',
            title: 'New comment',
            type: 'community_comment',
          },
          unread_count: 1,
        },
      });
    });

    expect(await screen.findByText('New realtime comment')).toBeTruthy();
    expect(getCommunityPost).toHaveBeenCalledTimes(2);
  });

  it('coalesces focus and visibility refreshes while a post refresh is in flight', async () => {
    render(
      <MemoryRouter
        initialEntries={['/apps/community/posts/post-1?channel=general']}
      >
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole('heading', { name: 'Post title' });
    await waitFor(() => expect(getCommunityPost).toHaveBeenCalledTimes(1));
    const initialDetail =
      await vi.mocked(getCommunityPost).mock.results[0].value;

    let resolveRefresh: (() => void) | undefined;
    vi.mocked(getCommunityPost).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRefresh = () => resolve(initialDetail);
        }),
    );

    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
      window.dispatchEvent(new Event('focus'));
    });

    expect(getCommunityPost).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveRefresh?.();
    });

    act(() => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(getCommunityPost).toHaveBeenCalledTimes(3));
  });

  it('uses readable channel metadata contrast classes', async () => {
    render(
      <MemoryRouter initialEntries={['/apps/community?channel=general']}>
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect((await screen.findByText('General channel')).className).toContain(
      'text-app-ink/70',
    );
    expect(screen.getByText('글 0개').className).toContain('text-app-ink/70');
  });

  it('does not mark a locked secret post as read', async () => {
    vi.mocked(getCommunityPost).mockResolvedValue({
      authorName: null,
      body: '',
      canModify: false,
      channelKey: 'general',
      commentCount: 0,
      comments: [],
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-locked',
      isAnonymous: true,
      isMine: false,
      isRead: false,
      isSecret: true,
      locked: true,
      lockedReason: 'password',
      title: '',
      updatedAt: '2026-06-29T00:00:00Z',
    });

    render(
      <MemoryRouter
        initialEntries={['/apps/community/posts/post-locked?channel=general']}
      >
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(getCommunityPost).toHaveBeenCalledWith('token', 'post-locked');
    });
    expect(markCommunityPostRead).not.toHaveBeenCalled();
  });

  it('uses the app confirm dialog instead of the browser system confirm for post deletion', async () => {
    const browserConfirm = vi
      .spyOn(window, 'confirm')
      .mockImplementation(() => {
        throw new Error('window.confirm should not be called');
      });

    render(
      <MemoryRouter
        initialEntries={['/apps/community/posts/post-1?channel=general']}
      >
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByRole('heading', { name: 'Post title' });

    fireEvent.click(screen.getByRole('button', { name: '삭제' }));

    expect(browserConfirm).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: '삭제' }));

    await waitFor(() => {
      expect(deleteCommunityPost).toHaveBeenCalledWith('token', 'post-1');
    });
  });

  it('uses the app confirm dialog instead of the browser system confirm for comment deletion', async () => {
    vi.mocked(getCommunityPost).mockResolvedValue({
      authorName: 'Author',
      body: 'Body',
      canModify: true,
      channelKey: 'general',
      commentCount: 1,
      comments: [
        {
          anonSeq: null,
          authorName: 'Commenter',
          body: 'Comment body',
          canModify: true,
          createdAt: '2026-06-29T00:00:00Z',
          id: 'comment-1',
          isAnonymous: false,
          isDeleted: false,
          parentCommentId: null,
          updatedAt: '2026-06-29T00:00:00Z',
        },
      ],
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-1',
      isAnonymous: false,
      isMine: true,
      isRead: false,
      isSecret: false,
      locked: false,
      lockedReason: null,
      title: 'Post title',
      updatedAt: '2026-06-29T00:00:00Z',
    });
    vi.mocked(deleteCommunityComment).mockResolvedValue(undefined);
    const browserConfirm = vi
      .spyOn(window, 'confirm')
      .mockImplementation(() => {
        throw new Error('window.confirm should not be called');
      });

    render(
      <MemoryRouter
        initialEntries={['/apps/community/posts/post-1?channel=general']}
      >
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText('Comment body');

    fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[1]);

    expect(browserConfirm).not.toHaveBeenCalled();
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: '삭제' }));

    await waitFor(() => {
      expect(deleteCommunityComment).toHaveBeenCalledWith(
        'token',
        'post-1',
        'comment-1',
      );
    });
  });

  it('filters the visible post rows only after submitting the search', async () => {
    const alphaPost = {
      authorName: 'Author',
      body: 'Body',
      canModify: false,
      channelKey: 'general',
      commentCount: 0,
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-alpha',
      isAnonymous: false,
      isMine: false,
      isRead: false,
      isSecret: false,
      locked: false,
      lockedReason: null,
      title: 'Alpha release',
      updatedAt: '2026-06-29T00:00:00Z',
    };
    const betaPost = {
      authorName: 'Maintainer',
      body: 'Body',
      canModify: false,
      channelKey: 'general',
      commentCount: 2,
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-beta',
      isAnonymous: false,
      isMine: false,
      isRead: true,
      isSecret: false,
      locked: false,
      lockedReason: null,
      title: 'Beta handbook',
      updatedAt: '2026-06-29T00:00:00Z',
    };
    vi.mocked(listCommunityPosts).mockImplementation(
      async (_token, _channelKey, options = {}) => ({
        page: 1,
        pageSize: 20,
        posts: options.search ? [betaPost] : [alphaPost, betaPost],
        total: options.search ? 1 : 2,
      }),
    );

    render(
      <MemoryRouter initialEntries={['/apps/community?channel=general']}>
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Alpha release')).not.toBeNull();
    expect(listCommunityPosts).toHaveBeenCalledWith('token', 'general', {
      page: 1,
      pageSize: 20,
      search: '',
    });
    const unreadTitle = screen.getByText('Alpha release');
    const readTitle = screen.getByText('Beta handbook');
    expect(unreadTitle.className).toContain('font-semibold');
    expect(readTitle.className).toContain('font-normal');
    const unreadStatusId = unreadTitle
      .closest('button')
      ?.getAttribute('aria-describedby');
    const readStatusId = readTitle
      .closest('button')
      ?.getAttribute('aria-describedby');
    expect(unreadStatusId).toBeTruthy();
    expect(readStatusId).toBeTruthy();
    expect(
      document.getElementById(unreadStatusId ?? '')?.textContent,
    ).toBeTruthy();
    expect(
      document.getElementById(readStatusId ?? '')?.textContent,
    ).toBeTruthy();
    expect(document.getElementById(unreadStatusId ?? '')?.textContent).not.toBe(
      document.getElementById(readStatusId ?? '')?.textContent,
    );

    const searchInput = screen.getByLabelText('글 검색') as HTMLInputElement;
    const initialPostFetchCount =
      vi.mocked(listCommunityPosts).mock.calls.length;
    searchInput.focus();
    fireEvent.change(searchInput, {
      target: { value: 'beta' },
    });

    await new Promise((resolve) => window.setTimeout(resolve, 350));
    expect(listCommunityPosts).toHaveBeenCalledTimes(initialPostFetchCount);
    expect(document.activeElement).toBe(searchInput);

    fireEvent.submit(searchInput.closest('form') as HTMLFormElement);

    await waitFor(() => {
      expect(listCommunityPosts).toHaveBeenLastCalledWith('token', 'general', {
        page: 1,
        pageSize: 20,
        search: 'beta',
      });
    });
    expect(screen.queryByText('Alpha release')).toBeNull();
    expect(screen.getByText('Beta handbook')).not.toBeNull();
  });

  it('disables search for private anonymous channels for regular users', async () => {
    vi.mocked(listCommunityChannels).mockResolvedValue({
      channels: [
        {
          active: true,
          adminOnlyContent: true,
          description: 'Private anonymous channel',
          forceAnonymous: true,
          id: 'channel-private',
          key: 'private',
          name: 'Private',
          position: 1,
          readOnly: false,
          templateBody: '',
          templateTitle: '',
        },
      ],
    });
    vi.mocked(listCommunityPosts).mockResolvedValue({
      page: 1,
      pageSize: 20,
      posts: [
        {
          authorName: null,
          body: '',
          canModify: false,
          channelKey: 'private',
          commentCount: 0,
          createdAt: '2026-06-29T00:00:00Z',
          id: 'post-private',
          isAnonymous: true,
          isMine: false,
          isRead: false,
          isSecret: false,
          locked: true,
          lockedReason: 'admin_only',
          title: '비공개 글입니다',
          updatedAt: '2026-06-29T00:00:00Z',
        },
      ],
      total: 1,
    });

    render(
      <MemoryRouter initialEntries={['/apps/community?channel=private']}>
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    const searchInput = await screen.findByLabelText('글 검색');
    expect((searchInput as HTMLInputElement).disabled).toBe(true);
    expect(searchInput.getAttribute('placeholder')).toBe(
      '비공개 익명 게시판은 검색할 수 없습니다.',
    );
    await waitFor(() => {
      expect(listCommunityPosts).toHaveBeenLastCalledWith('token', 'private', {
        page: 1,
        pageSize: 20,
        search: '',
      });
    });
  });

  it('applies channel templates and forced privacy settings when creating a post', async () => {
    vi.mocked(listCommunityChannels).mockResolvedValue({
      channels: [
        {
          active: true,
          adminOnlyContent: true,
          description: 'Private channel',
          forceAnonymous: true,
          id: 'channel-1',
          key: 'private',
          name: 'Private',
          position: 1,
          readOnly: false,
          templateBody: 'Template body',
          templateTitle: 'Template title',
        },
      ],
    });
    vi.mocked(createCommunityPost).mockResolvedValue({
      authorName: null,
      body: '',
      canModify: false,
      channelKey: 'private',
      commentCount: 0,
      createdAt: '2026-06-29T00:00:00Z',
      id: 'post-2',
      isAnonymous: true,
      isMine: true,
      isRead: false,
      isSecret: false,
      locked: true,
      lockedReason: 'admin_only',
      title: '',
      updatedAt: '2026-06-29T00:00:00Z',
    });

    render(
      <MemoryRouter initialEntries={['/apps/community?channel=private']}>
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '새 글' }));

    expect((screen.getByLabelText('제목') as HTMLInputElement).value).toBe(
      'Template title',
    );
    expect((screen.getByLabelText('본문') as HTMLTextAreaElement).value).toBe(
      'Template body',
    );

    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => {
      expect(createCommunityPost).toHaveBeenCalledWith('token', 'private', {
        body: 'Template body',
        isAnonymous: true,
        isSecret: false,
        password: null,
        title: 'Template title',
      });
    });
  });

  it('prevents composing in read-only channels for regular users', async () => {
    vi.mocked(listCommunityChannels).mockResolvedValue({
      channels: [
        {
          active: true,
          adminOnlyContent: false,
          description: 'Announcements',
          forceAnonymous: false,
          id: 'channel-read-only',
          key: 'announcements',
          name: 'Announcements',
          position: 1,
          readOnly: true,
          templateBody: '',
          templateTitle: '',
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={['/apps/community?channel=announcements']}>
        <Routes>
          <Route
            path="/apps/community/posts/:postId"
            element={<CommunityView />}
          />
          <Route path="/apps/community" element={<CommunityView />} />
        </Routes>
      </MemoryRouter>,
    );

    const newPostButton = await screen.findByRole('button', { name: '새 글' });

    expect((newPostButton as HTMLButtonElement).disabled).toBe(true);
    expect(
      screen.getByText(
        '읽기 전용 채널입니다. 글과 댓글을 등록하거나 수정할 수 없습니다.',
      ),
    ).toBeTruthy();

    fireEvent.click(newPostButton);

    expect(screen.queryByLabelText('제목')).toBeNull();
    expect(createCommunityPost).not.toHaveBeenCalled();
  });
});
