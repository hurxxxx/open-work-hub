import { describe, expect, it } from 'vitest';

import {
  buildCommunityListUrl,
  buildCommunityPostUrl,
  COMMUNITY_POST_ROUTE_PREFIX,
} from './community-url';

describe('community URL helpers', () => {
  it('builds the canonical list URL without a default channel query', () => {
    expect(buildCommunityListUrl()).toBe('/community');
    expect(buildCommunityListUrl('suggestions')).toBe('/community');
  });

  it('preserves non-default channel context on list URLs', () => {
    expect(buildCommunityListUrl('team-news')).toBe(
      '/community?channel=team-news',
    );
  });

  it('builds shareable post URLs', () => {
    expect(buildCommunityPostUrl('post-1')).toBe(
      `${COMMUNITY_POST_ROUTE_PREFIX}/post-1`,
    );
    expect(buildCommunityPostUrl('post 1', 'qna')).toBe(
      `${COMMUNITY_POST_ROUTE_PREFIX}/post%201?channel=qna`,
    );
  });
});
