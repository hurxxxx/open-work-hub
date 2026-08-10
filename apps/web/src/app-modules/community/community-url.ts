import { DEFAULT_COMMUNITY_CHANNEL_KEY } from './community-constants';

export const COMMUNITY_POST_ROUTE_PREFIX = '/community/posts';

export function buildCommunityListUrl(channelKey?: string | null): string {
  const normalizedChannel = normalizeCommunityChannelKey(channelKey);
  if (normalizedChannel === DEFAULT_COMMUNITY_CHANNEL_KEY) {
    return '/community';
  }
  return `/community?${communityChannelSearchParams(normalizedChannel)}`;
}

export function buildCommunityPostUrl(
  postId: string,
  channelKey?: string | null,
): string {
  const path = `${COMMUNITY_POST_ROUTE_PREFIX}/${encodeURIComponent(postId)}`;
  const normalizedChannel = normalizeCommunityChannelKey(channelKey);
  if (normalizedChannel === DEFAULT_COMMUNITY_CHANNEL_KEY) {
    return path;
  }
  return `${path}?${communityChannelSearchParams(normalizedChannel)}`;
}

function communityChannelSearchParams(channelKey: string): string {
  const params = new URLSearchParams();
  params.set('channel', channelKey);
  return params.toString();
}

function normalizeCommunityChannelKey(channelKey?: string | null): string {
  const normalized = channelKey?.trim();
  return normalized || DEFAULT_COMMUNITY_CHANNEL_KEY;
}
