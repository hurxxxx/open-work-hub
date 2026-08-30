import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Hash,
  Lock,
  MessageSquare,
  Pencil,
  Plus,
  Reply,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import {
  Button,
  IconButton,
  InlineNotice,
  Input,
  Select,
  useConfirm,
} from '@open-work-hub/ui';
import {
  NOTIFICATION_REALTIME_EVENT_TYPES,
  normalizeNotificationRealtimeEvent,
} from '@open-work-hub/contracts/notifications';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { authenticatedContentObjectUrl } from '@/src/platform/browser/browser-download';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { useRealtimeEvent } from '@/src/platform/realtime/realtime-provider';

import {
  createCommunityComment,
  createCommunityPost,
  deleteCommunityComment,
  deleteCommunityPost,
  getCommunityPost,
  listCommunityChannels,
  listCommunityPosts,
  markCommunityPostRead,
  resolveCommunityPostMediaUrls,
  unlockCommunityPost,
  updateCommunityComment,
  updateCommunityPost,
  type CommunityChannel,
  type CommunityComment,
  type CommunityPost,
  type CommunityPostDetail,
} from '../api/community-api';
import {
  CommunityMarkdownEditor,
  CommunityMarkdownViewer,
} from '@/src/platform/community/CommunityMarkdownEditor';
import { DEFAULT_COMMUNITY_CHANNEL_KEY } from '../community-constants';
import { buildCommunityListUrl, buildCommunityPostUrl } from '../community-url';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 30, 50, 100] as const;

type PostDraft = {
  title: string;
  body: string;
  isAnonymous: boolean;
  isSecret: boolean;
  password: string;
};

const EMPTY_POST_DRAFT: PostDraft = {
  title: '',
  body: '',
  isAnonymous: false,
  isSecret: false,
  password: '',
};

function postDraftFromChannel(channel: CommunityChannel | null): PostDraft {
  return {
    title: channel?.templateTitle ?? '',
    body: channel?.templateBody ?? '',
    isAnonymous: Boolean(channel?.forceAnonymous),
    isSecret: false,
    password: '',
  };
}

function lockedPostTitle(
  post: Pick<CommunityPost, 'lockedReason'>,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  return post.lockedReason === 'admin_only'
    ? t('community.adminOnlyTitle')
    : t('community.lockedTitle');
}

function authorLabel(
  comment: Pick<CommunityComment, 'anonSeq' | 'authorName' | 'isAnonymous'>,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  if (comment.authorName) {
    return comment.authorName;
  }
  if (comment.isAnonymous) {
    return comment.anonSeq
      ? t('community.anonymousAuthorNumber', { number: comment.anonSeq })
      : t('community.anonymousAuthor');
  }
  return comment.authorName || t('community.unknownAuthor');
}

function postAuthorLabel(
  post: Pick<CommunityPost, 'authorName' | 'isAnonymous'>,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  return (
    post.authorName ||
    (post.isAnonymous
      ? t('community.anonymousAuthor')
      : t('community.unknownAuthor'))
  );
}

export function CommunityView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const { resolveFileUrl, uploadFile } = useMediaUpload();
  const { confirm, confirmDialog } = useConfirm();
  const navigate = useNavigate();
  const { postId: routePostId } = useParams<{ postId?: string }>();
  const [searchParams] = useSearchParams();
  const activeChannelKey =
    searchParams.get('channel') || DEFAULT_COMMUNITY_CHANNEL_KEY;
  const selectedPostId = routePostId || null;

  const [channels, setChannels] = useState<CommunityChannel[]>([]);
  const [posts, setPosts] = useState<CommunityPost[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [postsLoading, setPostsLoading] = useState(true);
  const [postsError, setPostsError] = useState<string | null>(null);
  const [postSearch, setPostSearch] = useState('');
  const [appliedPostSearch, setAppliedPostSearch] = useState('');
  const [detail, setDetail] = useState<CommunityPostDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailMediaGenerationRef = useRef(0);
  const detailMediaObjectUrlsRef = useRef(new Set<string>());
  const [composerOpen, setComposerOpen] = useState(false);
  const [postDraft, setPostDraft] = useState<PostDraft>(EMPTY_POST_DRAFT);
  const [formError, setFormError] = useState<string | null>(null);
  const [submittingPost, setSubmittingPost] = useState(false);
  const [unlockPassword, setUnlockPassword] = useState('');
  const [unlocking, setUnlocking] = useState(false);
  const [unlockedPasswords, setUnlockedPasswords] = useState<
    Record<string, string>
  >({});
  const [commentBody, setCommentBody] = useState('');
  const [commentAnonymous, setCommentAnonymous] = useState(false);
  const [replyParentId, setReplyParentId] = useState<string | null>(null);
  const [commentError, setCommentError] = useState<string | null>(null);
  const [submittingComment, setSubmittingComment] = useState(false);
  const [editingPost, setEditingPost] = useState(false);
  const [editPostTitle, setEditPostTitle] = useState('');
  const [editPostBody, setEditPostBody] = useState('');
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editCommentBody, setEditCommentBody] = useState('');

  const activeChannel =
    channels.find((channel) => channel.key === activeChannelKey) ??
    channels[0] ??
    null;
  const canSearchHiddenCommunityFields = hasAdminConsoleAccess(user);
  const activeChannelReadOnly = Boolean(activeChannel?.readOnly);
  const canWriteActiveChannel =
    !activeChannelReadOnly || canSearchHiddenCommunityFields;
  const readOnlyNotice = canWriteActiveChannel
    ? t('community.readOnlyAdminNotice')
    : t('community.readOnlyNotice');
  const searchDisabled = Boolean(
    activeChannel?.adminOnlyContent &&
      activeChannel.forceAnonymous &&
      !canSearchHiddenCommunityFields,
  );
  const searchPlaceholderKey = searchDisabled
    ? 'community.searchDisabledPlaceholder'
    : activeChannel?.adminOnlyContent && !canSearchHiddenCommunityFields
      ? 'community.searchAuthorPlaceholder'
      : activeChannel?.forceAnonymous && !canSearchHiddenCommunityFields
        ? 'community.searchTitlePlaceholder'
        : 'community.searchPlaceholder';
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const activeChannelTitle = activeChannel
    ? t(`community.channels.${activeChannel.key}`, {
        defaultValue: activeChannel.name,
      })
    : t('community.title');
  const activeChannelDescription =
    activeChannel?.description || t('community.channelFallback');
  const hasPostSearch =
    !searchDisabled &&
    (postSearch.trim().length > 0 || appliedPostSearch.length > 0);
  const pageSizeSelectOptions = useMemo(
    () =>
      PAGE_SIZE_OPTIONS.map((size) => ({
        label: t('community.pageSizeOption', { count: size }),
        value: String(size),
      })),
    [t],
  );

  const openPost = useCallback(
    (
      postId: string,
      channelKey: string | null | undefined = activeChannelKey,
      options: { replace?: boolean } = {},
    ) => {
      navigate(buildCommunityPostUrl(postId, channelKey), {
        replace: options.replace,
      });
    },
    [activeChannelKey, navigate],
  );

  const openPostList = useCallback(
    (
      channelKey: string | null | undefined = activeChannelKey,
      options: { replace?: boolean } = {},
    ) => {
      navigate(buildCommunityListUrl(channelKey), {
        replace: options.replace,
      });
    },
    [activeChannelKey, navigate],
  );

  const loadChannels = useCallback(async (): Promise<CommunityChannel[]> => {
    try {
      const response = await listCommunityChannels(token);
      setChannels(response.channels);
      return response.channels;
    } catch {
      return [];
    }
  }, [token]);

  useEffect(() => {
    setPostSearch('');
    setAppliedPostSearch('');
  }, [activeChannelKey, searchDisabled]);

  const loadPosts = useCallback(
    async (targetPage: number) => {
      setPostsLoading(true);
      setPostsError(null);
      try {
        const response = await listCommunityPosts(token, activeChannelKey, {
          page: targetPage,
          pageSize,
          search: searchDisabled ? '' : appliedPostSearch,
        });
        if (response.posts.length === 0 && targetPage > 1) {
          await loadPosts(targetPage - 1);
          return;
        }
        setPosts(response.posts);
        setTotal(response.total);
        setPage(response.page);
      } catch {
        setPostsError(t('community.errors.postsFailed'));
        setPosts([]);
        setTotal(0);
      } finally {
        setPostsLoading(false);
      }
    },
    [activeChannelKey, appliedPostSearch, pageSize, searchDisabled, t, token],
  );

  const applyPostSearch = useCallback(() => {
    if (searchDisabled) return;
    setAppliedPostSearch(postSearch.trim());
    setPage(1);
  }, [postSearch, searchDisabled]);

  const reloadDetail = useCallback(
    async (postId: string) => {
      const password = unlockedPasswords[postId];
      const nextDetail = password
        ? await unlockCommunityPost(token, postId, password)
        : await getCommunityPost(token, postId);
      setDetail(nextDetail);
      return nextDetail;
    },
    [token, unlockedPasswords],
  );

  const refreshSelectedPost = useCallback(() => {
    if (!selectedPostId) return;
    void reloadDetail(selectedPostId).catch(() => undefined);
  }, [reloadDetail, selectedPostId]);

  const handleCommunityNotification = useCallback(
    (event: Parameters<typeof normalizeNotificationRealtimeEvent>[0]) => {
      const notificationEvent = normalizeNotificationRealtimeEvent(event);
      const notification = notificationEvent?.data.notification;
      if (
        !selectedPostId ||
        notification?.origin_app_id !== 'community' ||
        notification.source_type !== 'community_post' ||
        notification.source_id !== selectedPostId
      ) {
        return;
      }
      refreshSelectedPost();
    },
    [refreshSelectedPost, selectedPostId],
  );

  useRealtimeEvent(
    NOTIFICATION_REALTIME_EVENT_TYPES.created,
    handleCommunityNotification,
  );

  useEffect(() => {
    if (!selectedPostId) return;
    const refreshWhenVisible = () => {
      if (document.visibilityState !== 'hidden') {
        refreshSelectedPost();
      }
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [refreshSelectedPost, selectedPostId]);

  useEffect(() => {
    detailMediaGenerationRef.current += 1;
    const objectUrls = detailMediaObjectUrlsRef.current;
    return () => {
      detailMediaGenerationRef.current += 1;
      for (const objectUrl of objectUrls) URL.revokeObjectURL(objectUrl);
      objectUrls.clear();
    };
  }, [detail?.id, token]);

  const resolveDetailFileUrl = useCallback(
    async (url: string): Promise<string> => {
      if (!url.startsWith('media:')) {
        return resolveFileUrl ? resolveFileUrl(url) : url;
      }
      if (!detail) {
        return resolveFileUrl ? resolveFileUrl(url) : url;
      }
      if (!token) return url;

      try {
        const generation = detailMediaGenerationRef.current;
        const response = await resolveCommunityPostMediaUrls(
          token,
          detail.id,
          [url],
          detail.isSecret ? unlockedPasswords[detail.id] : null,
        );
        const contentUrl = response.resolved[url];
        if (contentUrl) {
          const objectUrl = await authenticatedContentObjectUrl(
            token,
            contentUrl,
          );
          if (detailMediaGenerationRef.current !== generation) {
            URL.revokeObjectURL(objectUrl);
            return url;
          }
          detailMediaObjectUrlsRef.current.add(objectUrl);
          return objectUrl;
        }
      } catch {
        return url;
      }

      return url;
    },
    [detail, resolveFileUrl, token, unlockedPasswords],
  );

  useEffect(() => {
    void loadChannels();
  }, [loadChannels]);

  useEffect(() => {
    setPage(1);
    if (!selectedPostId) {
      setDetail(null);
    }
    void loadPosts(1);
  }, [activeChannelKey, loadPosts, selectedPostId]);

  useEffect(() => {
    if (!selectedPostId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setDetailError(null);
    setEditingPost(false);
    setEditingCommentId(null);
    setReplyParentId(null);
    setCommentBody('');
    setUnlockPassword('');
    const loadedWithPassword = Boolean(unlockedPasswords[selectedPostId]);
    reloadDetail(selectedPostId)
      .then((nextDetail) => {
        if (nextDetail.channelKey !== activeChannelKey) {
          openPost(nextDetail.id, nextDetail.channelKey, { replace: true });
        }
        if (!loadedWithPassword && !nextDetail.locked && !nextDetail.isRead) {
          void markCommunityPostRead(token, nextDetail.id)
            .then(() => {
              setDetail((current) =>
                current?.id === nextDetail.id
                  ? { ...current, isRead: true }
                  : current,
              );
              setPosts((current) =>
                current.map((post) =>
                  post.id === nextDetail.id ? { ...post, isRead: true } : post,
                ),
              );
            })
            .catch(() => undefined);
        }
      })
      .catch(() => {
        setDetail(null);
        setDetailError(t('community.errors.detailFailed'));
      })
      .finally(() => setDetailLoading(false));
  }, [
    activeChannelKey,
    openPost,
    reloadDetail,
    selectedPostId,
    t,
    token,
    unlockedPasswords,
  ]);

  useEffect(() => {
    if (canWriteActiveChannel) return;
    setComposerOpen(false);
    setReplyParentId(null);
  }, [canWriteActiveChannel]);

  const commentGroups = useMemo(() => {
    const topLevel: CommunityComment[] = [];
    const repliesByParent = new Map<string, CommunityComment[]>();
    for (const comment of detail?.comments ?? []) {
      if (comment.parentCommentId) {
        const replies = repliesByParent.get(comment.parentCommentId) ?? [];
        replies.push(comment);
        repliesByParent.set(comment.parentCommentId, replies);
      } else {
        topLevel.push(comment);
      }
    }
    return { topLevel, repliesByParent };
  }, [detail]);

  const selectChannel = useCallback(
    (channelKey: string) => {
      openPostList(channelKey, { replace: true });
    },
    [openPostList],
  );

  useEffect(() => {
    if (channels.length === 0) return;
    if (channels.some((channel) => channel.key === activeChannelKey)) return;
    selectChannel(channels[0].key);
  }, [activeChannelKey, channels, selectChannel]);

  const resetComposer = useCallback(() => {
    setPostDraft(EMPTY_POST_DRAFT);
    setFormError(null);
    setComposerOpen(false);
  }, []);

  const openComposer = useCallback(() => {
    if (!canWriteActiveChannel) return;
    setPostDraft(postDraftFromChannel(activeChannel));
    setFormError(null);
    setComposerOpen(true);
  }, [activeChannel, canWriteActiveChannel]);

  const handleCreatePost = useCallback(async () => {
    if (submittingPost) return;
    if (!canWriteActiveChannel) {
      setFormError(t('community.readOnlyNotice'));
      return;
    }
    if (!postDraft.title.trim() || !postDraft.body.trim()) {
      setFormError(t('community.requiredFields'));
      return;
    }
    if (
      postDraft.isSecret &&
      !activeChannel?.adminOnlyContent &&
      !postDraft.password.trim()
    ) {
      setFormError(t('community.passwordRequired'));
      return;
    }
    setSubmittingPost(true);
    setFormError(null);
    try {
      const created = await createCommunityPost(token, activeChannelKey, {
        title: postDraft.title.trim(),
        body: postDraft.body.trim(),
        isAnonymous:
          Boolean(activeChannel?.forceAnonymous) || postDraft.isAnonymous,
        isSecret: activeChannel?.adminOnlyContent ? false : postDraft.isSecret,
        password:
          postDraft.isSecret && !activeChannel?.adminOnlyContent
            ? postDraft.password
            : null,
      });
      resetComposer();
      await loadPosts(1);
      openPost(created.id, created.channelKey);
    } catch {
      setFormError(t('community.errors.createFailed'));
    } finally {
      setSubmittingPost(false);
    }
  }, [
    activeChannelKey,
    activeChannel?.adminOnlyContent,
    activeChannel?.forceAnonymous,
    canWriteActiveChannel,
    loadPosts,
    openPost,
    postDraft,
    resetComposer,
    submittingPost,
    t,
    token,
  ]);

  const handleUnlock = useCallback(async () => {
    if (!detail || !unlockPassword.trim() || unlocking) return;
    setUnlocking(true);
    setDetailError(null);
    try {
      const unlocked = await unlockCommunityPost(
        token,
        detail.id,
        unlockPassword,
      );
      setUnlockedPasswords((current) => ({
        ...current,
        [detail.id]: unlockPassword,
      }));
      setDetail(unlocked);
      setPosts((current) =>
        current.map((post) =>
          post.id === unlocked.id ? { ...post, isRead: true } : post,
        ),
      );
    } catch {
      setDetailError(t('community.errors.unlockFailed'));
    } finally {
      setUnlocking(false);
    }
  }, [detail, t, token, unlocking, unlockPassword]);

  const handleCreateComment = useCallback(async () => {
    if (!detail || submittingComment) return;
    if (!canWriteActiveChannel) {
      setCommentError(t('community.readOnlyNotice'));
      return;
    }
    if (!commentBody.trim()) {
      setCommentError(t('community.requiredFields'));
      return;
    }
    setSubmittingComment(true);
    setCommentError(null);
    try {
      await createCommunityComment(token, detail.id, {
        body: commentBody.trim(),
        isAnonymous: Boolean(activeChannel?.forceAnonymous) || commentAnonymous,
        parentCommentId: replyParentId,
        password: detail.isSecret ? unlockedPasswords[detail.id] : null,
      });
      setCommentBody('');
      setReplyParentId(null);
      await reloadDetail(detail.id);
      await loadPosts(page);
    } catch {
      setCommentError(t('community.errors.commentFailed'));
    } finally {
      setSubmittingComment(false);
    }
  }, [
    commentAnonymous,
    commentBody,
    activeChannel?.forceAnonymous,
    canWriteActiveChannel,
    detail,
    loadPosts,
    page,
    reloadDetail,
    replyParentId,
    submittingComment,
    t,
    token,
    unlockedPasswords,
  ]);

  const startEditPost = useCallback(() => {
    if (!detail) return;
    setEditPostTitle(detail.title);
    setEditPostBody(detail.body);
    setEditingPost(true);
  }, [detail]);

  const savePostEdit = useCallback(async () => {
    if (!detail) return;
    try {
      await updateCommunityPost(token, detail.id, {
        title: editPostTitle.trim(),
        body: editPostBody.trim(),
      });
      setEditingPost(false);
      await reloadDetail(detail.id);
      await loadPosts(page);
    } catch {
      setDetailError(t('community.errors.updateFailed'));
    }
  }, [
    detail,
    editPostBody,
    editPostTitle,
    loadPosts,
    page,
    reloadDetail,
    t,
    token,
  ]);

  const deletePost = useCallback(async () => {
    if (!detail) return;
    const confirmed = await confirm({
      cancelLabel: t('community.cancel'),
      confirmLabel: t('community.delete'),
      description: t('community.confirmDeletePost'),
      title: t('community.delete'),
      variant: 'danger',
    });
    if (!confirmed) return;
    try {
      await deleteCommunityPost(token, detail.id);
      setDetail(null);
      openPostList(detail.channelKey);
      await loadPosts(page);
    } catch {
      setDetailError(t('community.errors.deleteFailed'));
    }
  }, [confirm, detail, loadPosts, openPostList, page, t, token]);

  const startEditComment = useCallback((comment: CommunityComment) => {
    setEditingCommentId(comment.id);
    setEditCommentBody(comment.body);
  }, []);

  const saveCommentEdit = useCallback(async () => {
    if (!detail || !editingCommentId) return;
    try {
      await updateCommunityComment(token, detail.id, editingCommentId, {
        body: editCommentBody.trim(),
      });
      setEditingCommentId(null);
      await reloadDetail(detail.id);
    } catch {
      setCommentError(t('community.errors.updateFailed'));
    }
  }, [detail, editCommentBody, editingCommentId, reloadDetail, t, token]);

  const deleteComment = useCallback(
    async (commentId: string) => {
      if (!detail) return;
      const confirmed = await confirm({
        cancelLabel: t('community.cancel'),
        confirmLabel: t('community.delete'),
        description: t('community.confirmDeleteComment'),
        title: t('community.delete'),
        variant: 'danger',
      });
      if (!confirmed) return;
      try {
        await deleteCommunityComment(token, detail.id, commentId);
        await reloadDetail(detail.id);
        await loadPosts(page);
      } catch {
        setCommentError(t('community.errors.deleteFailed'));
      }
    },
    [confirm, detail, loadPosts, page, reloadDetail, t, token],
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-app-bg text-app-ink">
      {confirmDialog}
      <main className="flex min-h-0 flex-1 flex-col">
        {!selectedPostId ? (
          <>
            <header className="border-b border-app-border bg-app-bg px-4 py-4">
              <div className="mx-auto flex w-full max-w-6xl items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 app-text-title text-app-ink">
                    <Hash size={18} className="shrink-0 text-app-ink/45" />
                    <span className="truncate">{activeChannelTitle}</span>
                  </div>
                  <div className="mt-1 app-text-body-sm text-app-ink/70">
                    {activeChannelDescription}
                  </div>
                  <div className="mt-1 app-text-caption text-app-ink/70">
                    {t('community.threadCount', { count: total })}
                  </div>
                  {activeChannelReadOnly ? (
                    <div className="mt-2 inline-flex max-w-full items-start gap-1.5 rounded-md border border-app-border bg-app-surface px-2 py-1 app-text-caption text-app-ink/60">
                      <Lock size={13} className="mt-0.5 shrink-0" />
                      <span>{readOnlyNotice}</span>
                    </div>
                  ) : null}
                </div>
                <Button
                  className="shrink-0"
                  disabled={!canWriteActiveChannel}
                  size="dense"
                  variant="primary"
                  onClick={openComposer}
                >
                  {canWriteActiveChannel ? (
                    <Plus size={15} />
                  ) : (
                    <Lock size={15} />
                  )}
                  {t('community.newPost')}
                </Button>
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto grid w-full max-w-6xl gap-3 px-4 py-4">
                {composerOpen && canWriteActiveChannel ? (
                  <PostComposer
                    channel={activeChannel}
                    draft={postDraft}
                    error={formError}
                    onCancel={resetComposer}
                    onChange={setPostDraft}
                    onSubmit={() => void handleCreatePost()}
                    resolveFileUrl={resolveFileUrl}
                    submitting={submittingPost}
                    t={t}
                    uploadFile={uploadFile}
                  />
                ) : null}

                {postsLoading ? (
                  <CenteredState>{t('community.loading')}</CenteredState>
                ) : postsError ? (
                  <InlineNotice tone="danger">{postsError}</InlineNotice>
                ) : posts.length === 0 && !hasPostSearch ? (
                  <CenteredState>{t('community.empty')}</CenteredState>
                ) : (
                  <>
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <form
                        className="flex w-full flex-col gap-2 sm:max-w-md sm:flex-row"
                        onSubmit={(event) => {
                          event.preventDefault();
                          applyPostSearch();
                        }}
                      >
                        <label className="relative min-w-0 flex-1">
                          <Search
                            aria-hidden="true"
                            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/35"
                            size={15}
                          />
                          <Input
                            aria-label={t('community.searchInput')}
                            className="pl-9"
                            disabled={searchDisabled}
                            placeholder={t(searchPlaceholderKey)}
                            value={postSearch}
                            onChange={(event) =>
                              setPostSearch(event.target.value)
                            }
                          />
                        </label>
                        <Button
                          disabled={searchDisabled}
                          size="dense"
                          type="submit"
                          variant="secondary"
                        >
                          <Search size={15} />
                          {t('common:actions.search')}
                        </Button>
                      </form>
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="app-text-caption text-app-ink/45">
                          {t('community.searchResultCount', {
                            count: posts.length,
                            total,
                          })}
                        </span>
                        <label className="flex items-center gap-2 app-text-caption text-app-ink/55">
                          <span>{t('community.pageSizeLabel')}</span>
                          <Select
                            className="min-w-[116px]"
                            options={pageSizeSelectOptions}
                            value={String(pageSize)}
                            onValueChange={(value) => {
                              const nextSize = Number(value);
                              if (
                                PAGE_SIZE_OPTIONS.includes(
                                  nextSize as (typeof PAGE_SIZE_OPTIONS)[number],
                                )
                              ) {
                                setPageSize(nextSize);
                              }
                            }}
                          />
                        </label>
                      </div>
                    </div>
                    <div className="overflow-hidden rounded-md border border-app-border bg-app-surface shadow-sm">
                      <div className="hidden border-b border-app-border bg-app-bg/60 px-4 py-2 app-text-micro font-semibold text-app-ink/45 sm:grid sm:grid-cols-[minmax(0,1fr)_108px_minmax(96px,140px)_150px] sm:gap-3">
                        <span>{t('community.listColumnTitle')}</span>
                        <span className="text-right">
                          {t('community.listColumnComments')}
                        </span>
                        <span>{t('community.listColumnAuthor')}</span>
                        <span className="text-right">
                          {t('community.listColumnDate')}
                        </span>
                      </div>
                      {posts.length === 0 ? (
                        <CenteredState>
                          {t('community.noSearchResults')}
                        </CenteredState>
                      ) : (
                        posts.map((post) => (
                          <PostListItem
                            key={post.id}
                            onClick={() => openPost(post.id, post.channelKey)}
                            post={post}
                            t={t}
                          />
                        ))
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>

            <footer className="border-t border-app-border bg-app-bg px-4 py-2">
              <div className="mx-auto flex w-full max-w-6xl items-center justify-between">
                <Button
                  disabled={page <= 1}
                  onClick={() => void loadPosts(page - 1)}
                  size="dense"
                  variant="ghost"
                >
                  <ChevronLeft size={16} />
                  {t('community.previousPage')}
                </Button>
                <span className="app-text-caption text-app-ink/55">
                  {t('community.pageLabel', { page, pageCount })}
                </span>
                <Button
                  disabled={page >= pageCount}
                  onClick={() => void loadPosts(page + 1)}
                  size="dense"
                  variant="ghost"
                >
                  {t('community.nextPage')}
                  <ChevronRight size={16} />
                </Button>
              </div>
            </footer>
          </>
        ) : detailLoading ? (
          <CenteredState>{t('community.loading')}</CenteredState>
        ) : detailError && !detail ? (
          <div className="p-5">
            <InlineNotice tone="danger">{detailError}</InlineNotice>
          </div>
        ) : detail ? (
          <>
            <header className="border-b border-app-border bg-app-bg px-4 py-4">
              <div className="mx-auto flex w-full max-w-5xl items-start gap-3">
                <IconButton
                  aria-label={t('community.backToPosts')}
                  onClick={() => openPostList(detail.channelKey)}
                  variant="ghost"
                >
                  <ArrowLeft size={17} />
                </IconButton>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2 app-text-caption text-app-ink/45">
                    <Hash size={14} />
                    <span className="truncate">{activeChannelTitle}</span>
                  </div>
                  {editingPost ? (
                    <div className="grid gap-2">
                      <Input
                        aria-label={t('community.titleInput')}
                        maxLength={240}
                        value={editPostTitle}
                        onChange={(event) =>
                          setEditPostTitle(event.target.value)
                        }
                      />
                      <CommunityMarkdownEditor
                        ariaLabel={t('community.bodyInput')}
                        minHeight={320}
                        onChange={setEditPostBody}
                        placeholder={t('community.bodyPlaceholder')}
                        resolveFileUrl={resolveFileUrl}
                        uploadFile={uploadFile}
                        value={editPostBody}
                      />
                    </div>
                  ) : (
                    <>
                      <div className="flex min-w-0 items-center gap-2">
                        {detail.isSecret ? (
                          <Lock
                            size={16}
                            className="shrink-0 text-app-ink/45"
                          />
                        ) : null}
                        <h1 className="app-text-title min-w-0 truncate text-app-ink">
                          {detail.locked
                            ? lockedPostTitle(detail, t)
                            : detail.title}
                        </h1>
                      </div>
                      <div className="app-text-caption text-app-ink/50">
                        {detail.authorName ||
                          (detail.isAnonymous
                            ? t('community.anonymousAuthor')
                            : t('community.unknownAuthor'))}
                        {' · '}
                        <UserDateTime value={detail.createdAt} />
                      </div>
                    </>
                  )}
                </div>
                {detail.canModify && !detail.locked ? (
                  <div className="flex shrink-0 items-center gap-1">
                    {editingPost ? (
                      <>
                        <Button
                          variant="primary"
                          onClick={() => void savePostEdit()}
                        >
                          {t('community.save')}
                        </Button>
                        <IconButton
                          aria-label={t('community.cancel')}
                          onClick={() => setEditingPost(false)}
                          variant="ghost"
                        >
                          <X size={16} />
                        </IconButton>
                      </>
                    ) : (
                      <>
                        <IconButton
                          aria-label={t('community.edit')}
                          onClick={startEditPost}
                          variant="ghost"
                        >
                          <Pencil size={16} />
                        </IconButton>
                        <IconButton
                          aria-label={t('community.delete')}
                          onClick={() => void deletePost()}
                          variant="ghost"
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </>
                    )}
                  </div>
                ) : null}
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-5xl px-4 py-5">
                {detailError ? (
                  <InlineNotice className="mb-3" tone="danger">
                    {detailError}
                  </InlineNotice>
                ) : null}

                {detail.locked ? (
                  detail.lockedReason === 'admin_only' ? (
                    <AdminOnlyPostPanel t={t} />
                  ) : (
                    <LockedPostPanel
                      onSubmit={() => void handleUnlock()}
                      password={unlockPassword}
                      setPassword={setUnlockPassword}
                      submitting={unlocking}
                      t={t}
                    />
                  )
                ) : (
                  <>
                    <article className="border-b border-app-border pb-5">
                      <CommunityMarkdownViewer
                        className="prose-base text-app-ink/85"
                        markdown={detail.body}
                        resolveFileUrl={resolveDetailFileUrl}
                      />
                    </article>
                    <section className="py-4">
                      <div className="mb-3 flex items-center gap-2 app-text-body-sm font-semibold">
                        <MessageSquare size={16} className="text-app-ink/50" />
                        {t('community.comments', {
                          count: detail.commentCount,
                        })}
                      </div>
                      <div className="grid gap-3">
                        {commentGroups.topLevel.map((comment) => (
                          <CommentThread
                            comment={comment}
                            canReply={canWriteActiveChannel}
                            editBody={editCommentBody}
                            editingCommentId={editingCommentId}
                            key={comment.id}
                            onCancelEdit={() => setEditingCommentId(null)}
                            onDelete={(commentId) =>
                              void deleteComment(commentId)
                            }
                            onEdit={startEditComment}
                            onEditBodyChange={setEditCommentBody}
                            onReply={(commentId) => setReplyParentId(commentId)}
                            onSaveEdit={() => void saveCommentEdit()}
                            resolveFileUrl={resolveDetailFileUrl}
                            replies={
                              commentGroups.repliesByParent.get(comment.id) ??
                              []
                            }
                            t={t}
                            uploadFile={uploadFile}
                          />
                        ))}
                        {detail.comments.length === 0 ? (
                          <div className="rounded-md border border-dashed border-app-border px-3 py-4 text-center app-text-body-sm text-app-ink/45">
                            {t('community.noComments')}
                          </div>
                        ) : null}
                      </div>
                    </section>
                  </>
                )}
              </div>
            </div>

            {!detail.locked && canWriteActiveChannel ? (
              <CommentComposer
                anonymous={commentAnonymous}
                body={commentBody}
                error={commentError}
                forceAnonymous={Boolean(activeChannel?.forceAnonymous)}
                onAnonymousChange={setCommentAnonymous}
                onBodyChange={setCommentBody}
                onCancelReply={() => setReplyParentId(null)}
                onSubmit={() => void handleCreateComment()}
                replying={Boolean(replyParentId)}
                resolveFileUrl={resolveFileUrl}
                submitting={submittingComment}
                t={t}
                uploadFile={uploadFile}
              />
            ) : !detail.locked && activeChannelReadOnly ? (
              <footer className="border-t border-app-border bg-app-bg px-4 py-3">
                <div className="mx-auto w-full max-w-5xl pr-16">
                  <InlineNotice tone="info">{readOnlyNotice}</InlineNotice>
                </div>
              </footer>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}

function CenteredState({ children }: { children: string }) {
  return (
    <div className="flex h-full min-h-40 items-center justify-center px-4 text-center app-text-body-sm text-app-ink/45">
      {children}
    </div>
  );
}

function PostComposer({
  channel,
  draft,
  error,
  onCancel,
  onChange,
  onSubmit,
  resolveFileUrl,
  submitting,
  t,
  uploadFile,
}: {
  channel: CommunityChannel | null;
  draft: PostDraft;
  error: string | null;
  onCancel: () => void;
  onChange: (next: PostDraft) => void;
  onSubmit: () => void;
  resolveFileUrl?: (url: string) => Promise<string>;
  submitting: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  uploadFile?: (file: File) => Promise<string>;
}) {
  return (
    <div className="grid gap-3 rounded-md border border-app-border bg-app-surface px-4 py-3 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="app-text-body-sm font-semibold">
          {t('community.newPost')}
        </span>
        <IconButton
          aria-label={t('community.cancel')}
          onClick={onCancel}
          variant="ghost"
        >
          <X size={16} />
        </IconButton>
      </div>
      <Input
        aria-label={t('community.titleInput')}
        maxLength={240}
        placeholder={t('community.titlePlaceholder')}
        value={draft.title}
        onChange={(event) => onChange({ ...draft, title: event.target.value })}
      />
      <CommunityMarkdownEditor
        ariaLabel={t('community.bodyInput')}
        minHeight={320}
        onChange={(body) => onChange({ ...draft, body })}
        placeholder={t('community.bodyPlaceholder')}
        resolveFileUrl={resolveFileUrl}
        uploadFile={uploadFile}
        value={draft.body}
      />
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 app-text-control-sm text-app-ink/70">
          <input
            checked={channel?.forceAnonymous || draft.isAnonymous}
            disabled={channel?.forceAnonymous}
            onChange={(event) =>
              onChange({ ...draft, isAnonymous: event.target.checked })
            }
            type="checkbox"
          />
          {channel?.forceAnonymous
            ? t('community.forceAnonymous')
            : t('community.anonymous')}
        </label>
        {channel?.adminOnlyContent ? (
          <span className="inline-flex items-center gap-1 app-text-control-sm text-app-ink/70">
            <Lock size={14} />
            {t('community.adminOnly')}
          </span>
        ) : (
          <label className="flex items-center gap-2 app-text-control-sm text-app-ink/70">
            <input
              checked={draft.isSecret}
              onChange={(event) =>
                onChange({ ...draft, isSecret: event.target.checked })
              }
              type="checkbox"
            />
            <Lock size={14} />
            {t('community.secret')}
          </label>
        )}
      </div>
      {draft.isSecret && !channel?.adminOnlyContent ? (
        <Input
          autoComplete="new-password"
          aria-label={t('community.passwordInput')}
          placeholder={t('community.passwordPlaceholder')}
          type="password"
          value={draft.password}
          onChange={(event) =>
            onChange({ ...draft, password: event.target.value })
          }
        />
      ) : null}
      {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
      <div className="flex justify-end gap-2">
        <Button onClick={onCancel} variant="ghost">
          {t('community.cancel')}
        </Button>
        <Button disabled={submitting} onClick={onSubmit} variant="primary">
          {submitting ? t('community.submitting') : t('community.submit')}
        </Button>
      </div>
    </div>
  );
}

function PostListItem({
  onClick,
  post,
  t,
}: {
  onClick: () => void;
  post: CommunityPost;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  const readStatusId = useId();
  const title = post.locked ? lockedPostTitle(post, t) : post.title;
  const author = postAuthorLabel(post, t);
  const commentCount = t('community.commentCount', {
    count: post.commentCount,
  });
  return (
    <button
      aria-describedby={readStatusId}
      aria-label={t('community.openPost', { title })}
      className="w-full border-b border-app-border px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-inset focus:ring-app-accent/30 sm:grid sm:grid-cols-[minmax(0,1fr)_108px_minmax(96px,140px)_150px] sm:items-center sm:gap-3"
      onClick={onClick}
      type="button"
    >
      <div className="flex min-w-0 items-center gap-2">
        {post.locked || post.isSecret ? (
          <Lock size={14} className="shrink-0 text-app-ink/45" />
        ) : null}
        <span
          className={`truncate app-text-body-sm ${
            post.isRead
              ? 'font-normal text-app-ink/65'
              : 'font-semibold text-app-ink'
          }`}
        >
          {title}
        </span>
        <span className="sr-only" id={readStatusId}>
          {post.isRead
            ? t('community.readStatus')
            : t('community.unreadStatus')}
        </span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 app-text-caption text-app-ink/45 sm:hidden">
        <span className="inline-flex items-center gap-1 whitespace-nowrap">
          <MessageSquare size={14} />
          {commentCount}
        </span>
        <span>{author}</span>
        <span className="whitespace-nowrap">
          <UserDateTime value={post.createdAt} />
        </span>
      </div>
      <span className="hidden items-center justify-end gap-1 whitespace-nowrap app-text-caption text-app-ink/45 sm:inline-flex">
        <MessageSquare size={14} />
        {commentCount}
      </span>
      <span className="hidden truncate app-text-caption text-app-ink/45 sm:block">
        {author}
      </span>
      <span className="hidden whitespace-nowrap text-right app-text-micro text-app-ink/40 sm:block">
        <UserDateTime value={post.createdAt} />
      </span>
    </button>
  );
}

function LockedPostPanel({
  onSubmit,
  password,
  setPassword,
  submitting,
  t,
}: {
  onSubmit: () => void;
  password: string;
  setPassword: (value: string) => void;
  submitting: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  return (
    <div className="mx-auto grid max-w-sm gap-3 rounded-md border border-app-border bg-app-surface px-4 py-4">
      <div className="flex items-center gap-2 app-text-body-sm font-semibold">
        <Lock size={16} className="text-app-ink/55" />
        {t('community.lockedTitle')}
      </div>
      <Input
        autoComplete="current-password"
        aria-label={t('community.passwordInput')}
        placeholder={t('community.passwordPlaceholder')}
        type="password"
        value={password}
        onChange={(event) => setPassword(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') onSubmit();
        }}
      />
      <Button
        disabled={submitting || !password.trim()}
        onClick={onSubmit}
        variant="primary"
      >
        {submitting ? t('community.unlocking') : t('community.unlock')}
      </Button>
    </div>
  );
}

function AdminOnlyPostPanel({
  t,
}: {
  t: (key: string, options?: Record<string, unknown>) => string;
}) {
  return (
    <div className="mx-auto grid max-w-sm gap-2 rounded-md border border-app-border bg-app-surface px-4 py-4">
      <div className="flex items-center gap-2 app-text-body-sm font-semibold">
        <Lock size={16} className="text-app-ink/55" />
        {t('community.adminOnlyTitle')}
      </div>
      <p className="app-text-body-sm text-app-ink/60">
        {t('community.adminOnlyBody')}
      </p>
    </div>
  );
}

function CommentThread({
  canReply,
  comment,
  editBody,
  editingCommentId,
  onCancelEdit,
  onDelete,
  onEdit,
  onEditBodyChange,
  onReply,
  onSaveEdit,
  resolveFileUrl,
  replies,
  t,
  uploadFile,
}: {
  canReply: boolean;
  comment: CommunityComment;
  editBody: string;
  editingCommentId: string | null;
  onCancelEdit: () => void;
  onDelete: (commentId: string) => void;
  onEdit: (comment: CommunityComment) => void;
  onEditBodyChange: (value: string) => void;
  onReply: (commentId: string) => void;
  onSaveEdit: () => void;
  resolveFileUrl?: (url: string) => Promise<string>;
  replies: CommunityComment[];
  t: (key: string, options?: Record<string, unknown>) => string;
  uploadFile?: (file: File) => Promise<string>;
}) {
  return (
    <div className="grid gap-2">
      <CommentRow
        canReply={canReply}
        comment={comment}
        editBody={editBody}
        editing={editingCommentId === comment.id}
        onCancelEdit={onCancelEdit}
        onDelete={onDelete}
        onEdit={onEdit}
        onEditBodyChange={onEditBodyChange}
        onReply={onReply}
        onSaveEdit={onSaveEdit}
        resolveFileUrl={resolveFileUrl}
        t={t}
        uploadFile={uploadFile}
      />
      {replies.length > 0 ? (
        <div className="ml-6 grid gap-2 border-l border-app-border pl-3">
          {replies.map((reply) => (
            <CommentRow
              canReply={canReply}
              comment={reply}
              editBody={editBody}
              editing={editingCommentId === reply.id}
              key={reply.id}
              onCancelEdit={onCancelEdit}
              onDelete={onDelete}
              onEdit={onEdit}
              onEditBodyChange={onEditBodyChange}
              onReply={onReply}
              onSaveEdit={onSaveEdit}
              resolveFileUrl={resolveFileUrl}
              t={t}
              uploadFile={uploadFile}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function CommentRow({
  canReply,
  comment,
  editBody,
  editing,
  onCancelEdit,
  onDelete,
  onEdit,
  onEditBodyChange,
  onReply,
  onSaveEdit,
  resolveFileUrl,
  t,
  uploadFile,
}: {
  canReply: boolean;
  comment: CommunityComment;
  editBody: string;
  editing: boolean;
  onCancelEdit: () => void;
  onDelete: (commentId: string) => void;
  onEdit: (comment: CommunityComment) => void;
  onEditBodyChange: (value: string) => void;
  onReply: (commentId: string) => void;
  onSaveEdit: () => void;
  resolveFileUrl?: (url: string) => Promise<string>;
  t: (key: string, options?: Record<string, unknown>) => string;
  uploadFile?: (file: File) => Promise<string>;
}) {
  return (
    <div className="group rounded-md px-2 py-2 hover:bg-app-surface-hover">
      <div className="mb-1 flex items-center gap-2">
        <span className="app-text-body-sm font-semibold text-app-ink">
          {comment.isDeleted
            ? t('community.deletedAuthor')
            : authorLabel(comment, t)}
        </span>
        <span className="app-text-micro text-app-ink/40">
          <UserDateTime value={comment.createdAt} />
        </span>
        {!comment.isDeleted ? (
          <div className="ml-auto flex opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            {canReply ? (
              <IconButton
                aria-label={t('community.reply')}
                onClick={() => onReply(comment.id)}
                variant="ghost"
              >
                <Reply size={14} />
              </IconButton>
            ) : null}
            {comment.canModify ? (
              <>
                <IconButton
                  aria-label={t('community.edit')}
                  onClick={() => onEdit(comment)}
                  variant="ghost"
                >
                  <Pencil size={14} />
                </IconButton>
                <IconButton
                  aria-label={t('community.delete')}
                  onClick={() => onDelete(comment.id)}
                  variant="ghost"
                >
                  <Trash2 size={14} />
                </IconButton>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
      {comment.isDeleted ? (
        <p className="app-text-body-sm italic text-app-ink/45">
          {t('community.deletedComment')}
        </p>
      ) : editing ? (
        <div className="grid gap-2">
          <CommunityMarkdownEditor
            ariaLabel={t('community.commentInput')}
            compact
            minHeight={160}
            onChange={onEditBodyChange}
            placeholder={t('community.commentPlaceholder')}
            resolveFileUrl={resolveFileUrl}
            uploadFile={uploadFile}
            value={editBody}
          />
          <div className="flex justify-end gap-2">
            <Button onClick={onCancelEdit} variant="ghost">
              {t('community.cancel')}
            </Button>
            <Button onClick={onSaveEdit} variant="primary">
              {t('community.save')}
            </Button>
          </div>
        </div>
      ) : (
        <CommunityMarkdownViewer
          className="text-app-ink/75"
          markdown={comment.body}
          resolveFileUrl={resolveFileUrl}
        />
      )}
    </div>
  );
}

function CommentComposer({
  anonymous,
  body,
  error,
  forceAnonymous,
  onAnonymousChange,
  onBodyChange,
  onCancelReply,
  onSubmit,
  replying,
  resolveFileUrl,
  submitting,
  t,
  uploadFile,
}: {
  anonymous: boolean;
  body: string;
  error: string | null;
  forceAnonymous: boolean;
  onAnonymousChange: (value: boolean) => void;
  onBodyChange: (value: string) => void;
  onCancelReply: () => void;
  onSubmit: () => void;
  replying: boolean;
  resolveFileUrl?: (url: string) => Promise<string>;
  submitting: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  uploadFile?: (file: File) => Promise<string>;
}) {
  return (
    <footer className="border-t border-app-border bg-app-bg px-4 py-3">
      <div className="mx-auto grid w-full max-w-5xl gap-2 pr-16">
        {replying ? (
          <div className="flex items-center justify-between rounded-md bg-app-surface px-2 py-1 app-text-caption text-app-ink/60">
            <span>{t('community.replying')}</span>
            <button
              aria-label={t('community.cancelReply')}
              className="rounded p-1 hover:bg-app-surface-hover"
              onClick={onCancelReply}
              type="button"
            >
              <X size={13} />
            </button>
          </div>
        ) : null}
        <CommunityMarkdownEditor
          ariaLabel={t('community.commentInput')}
          compact
          minHeight={180}
          onChange={onBodyChange}
          placeholder={t('community.commentPlaceholder')}
          resolveFileUrl={resolveFileUrl}
          uploadFile={uploadFile}
          value={body}
        />
        {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2 app-text-control-sm text-app-ink/65">
            <input
              checked={forceAnonymous || anonymous}
              disabled={forceAnonymous}
              onChange={(event) => onAnonymousChange(event.target.checked)}
              type="checkbox"
            />
            {forceAnonymous
              ? t('community.forceAnonymous')
              : t('community.anonymous')}
          </label>
          <Button
            disabled={submitting || !body.trim()}
            onClick={onSubmit}
            variant="primary"
          >
            {submitting ? t('community.posting') : t('community.comment')}
          </Button>
        </div>
      </div>
    </footer>
  );
}
