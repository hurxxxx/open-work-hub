import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import { DEFAULT_COMMUNITY_CHANNEL_KEY } from './community-constants';

export function buildCommunityListUrl(channelKey?: string | null): string {
  const normalizedChannel = normalizeCommunityChannelKey(channelKey);
  return buildAppHref({
    routeId: 'community.root',
    queryParams: {
      channel:
        normalizedChannel === DEFAULT_COMMUNITY_CHANNEL_KEY
          ? null
          : normalizedChannel,
    },
  });
}

export function buildCommunityPostUrl(
  postId: string,
  channelKey?: string | null,
): string {
  const normalizedChannel = normalizeCommunityChannelKey(channelKey);
  return buildAppHref({
    routeId: 'community.post',
    pathParams: { postId },
    queryParams: {
      channel:
        normalizedChannel === DEFAULT_COMMUNITY_CHANNEL_KEY
          ? null
          : normalizedChannel,
    },
  });
}

function normalizeCommunityChannelKey(channelKey?: string | null): string {
  const normalized = channelKey?.trim();
  return normalized || DEFAULT_COMMUNITY_CHANNEL_KEY;
}
