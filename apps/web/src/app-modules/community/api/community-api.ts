import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import { COMMUNITY_CHANNELS_CHANGED_EVENT } from '@/src/platform/community/community-channel-events';

export interface CommunityChannel {
  id: string;
  key: string;
  name: string;
  description: string;
  position: number;
  active: boolean;
  readOnly: boolean;
  forceAnonymous: boolean;
  adminOnlyContent: boolean;
  templateTitle: string;
  templateBody: string;
}

export interface CommunityChannelsResponse {
  channels: CommunityChannel[];
}

export interface CommunityPost {
  id: string;
  channelKey: string;
  title: string;
  body: string;
  isAnonymous: boolean;
  isSecret: boolean;
  locked: boolean;
  lockedReason: 'password' | 'admin_only' | null;
  isMine: boolean;
  isRead: boolean;
  canModify: boolean;
  authorName: string | null;
  commentCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface CommunityComment {
  id: string;
  body: string;
  isAnonymous: boolean;
  isDeleted: boolean;
  parentCommentId: string | null;
  authorName: string | null;
  anonSeq: number | null;
  canModify: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CommunityPostDetail extends CommunityPost {
  comments: CommunityComment[];
}

export interface CommunityMediaResolveResponse {
  resolved: Record<string, string>;
}

export interface CommunityPostListResponse {
  posts: CommunityPost[];
  total: number;
  page: number;
  pageSize: number;
}

export interface CommunityPostCreateInput {
  title: string;
  body: string;
  isAnonymous: boolean;
  isSecret: boolean;
  password?: string | null;
}

export interface CommunityPostUpdateInput {
  title: string;
  body: string;
}

export interface CommunityCommentCreateInput {
  body: string;
  isAnonymous: boolean;
  password?: string | null;
  parentCommentId?: string | null;
}

export interface CommunityCommentUpdateInput {
  body: string;
}

export class CommunityApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'CommunityApiError';
  }
}

async function request<T>(
  path: string,
  token: string | null | undefined,
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    path,
    token,
    init,
    (error) =>
      new CommunityApiError(
        error.status,
        error.message || `Community request failed with ${error.status}.`,
      ),
  );
}

let cachedCommunityChannels: CommunityChannelsResponse | null = null;
let communityChannelsRequest: Promise<CommunityChannelsResponse> | null = null;

function cloneCommunityChannelsResponse(
  response: CommunityChannelsResponse,
): CommunityChannelsResponse {
  return {
    channels: response.channels.map((channel) => ({ ...channel })),
  };
}

export function invalidateCommunityChannelsCache(): void {
  cachedCommunityChannels = null;
  communityChannelsRequest = null;
}

if (typeof window !== 'undefined') {
  window.addEventListener(
    COMMUNITY_CHANNELS_CHANGED_EVENT,
    invalidateCommunityChannelsCache,
  );
}

export function listCommunityChannels(
  token: string | null | undefined,
  options: { forceRefresh?: boolean } = {},
): Promise<CommunityChannelsResponse> {
  if (!options.forceRefresh && cachedCommunityChannels) {
    return Promise.resolve(
      cloneCommunityChannelsResponse(cachedCommunityChannels),
    );
  }

  if (!options.forceRefresh && communityChannelsRequest) {
    return communityChannelsRequest.then(cloneCommunityChannelsResponse);
  }

  const nextRequest = request<CommunityChannelsResponse>(
    '/api/v1/community/channels',
    token,
  )
    .then((response) => {
      cachedCommunityChannels = cloneCommunityChannelsResponse(response);
      return cloneCommunityChannelsResponse(cachedCommunityChannels);
    })
    .finally(() => {
      if (communityChannelsRequest === nextRequest) {
        communityChannelsRequest = null;
      }
    });
  communityChannelsRequest = nextRequest;
  return nextRequest;
}

export function listCommunityPosts(
  token: string | null | undefined,
  channelKey: string,
  options: { page?: number; pageSize?: number; search?: string } = {},
): Promise<CommunityPostListResponse> {
  const params = new URLSearchParams();
  if (options.page) params.set('page', String(options.page));
  if (options.pageSize) params.set('page_size', String(options.pageSize));
  if (options.search?.trim()) params.set('q', options.search.trim());
  const query = params.toString();
  return request<CommunityPostListResponse>(
    `/api/v1/community/channels/${encodeURIComponent(channelKey)}/posts${query ? `?${query}` : ''}`,
    token,
  );
}

export function createCommunityPost(
  token: string | null | undefined,
  channelKey: string,
  payload: CommunityPostCreateInput,
): Promise<CommunityPost> {
  return request<CommunityPost>(
    `/api/v1/community/channels/${encodeURIComponent(channelKey)}/posts`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function getCommunityPost(
  token: string | null | undefined,
  postId: string,
): Promise<CommunityPostDetail> {
  return request<CommunityPostDetail>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}`,
    token,
  );
}

export function markCommunityPostRead(
  token: string | null | undefined,
  postId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}/read`,
    token,
    { method: 'POST' },
  );
}

export function unlockCommunityPost(
  token: string | null | undefined,
  postId: string,
  password: string,
): Promise<CommunityPostDetail> {
  return request<CommunityPostDetail>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}/unlock`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ password }),
    },
  );
}

export function resolveCommunityPostMediaUrls(
  token: string | null | undefined,
  postId: string,
  urls: string[],
  password?: string | null,
): Promise<CommunityMediaResolveResponse> {
  return request<CommunityMediaResolveResponse>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}/media/resolve`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ urls, password: password || null }),
    },
  );
}

export function updateCommunityPost(
  token: string | null | undefined,
  postId: string,
  payload: CommunityPostUpdateInput,
): Promise<CommunityPost> {
  return request<CommunityPost>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteCommunityPost(
  token: string | null | undefined,
  postId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}`,
    token,
    { method: 'DELETE' },
  );
}

export function createCommunityComment(
  token: string | null | undefined,
  postId: string,
  payload: CommunityCommentCreateInput,
): Promise<CommunityComment> {
  return request<CommunityComment>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}/comments`,
    token,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updateCommunityComment(
  token: string | null | undefined,
  postId: string,
  commentId: string,
  payload: CommunityCommentUpdateInput,
): Promise<CommunityComment> {
  return request<CommunityComment>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}/comments/${encodeURIComponent(commentId)}`,
    token,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteCommunityComment(
  token: string | null | undefined,
  postId: string,
  commentId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/community/posts/${encodeURIComponent(postId)}/comments/${encodeURIComponent(commentId)}`,
    token,
    { method: 'DELETE' },
  );
}
