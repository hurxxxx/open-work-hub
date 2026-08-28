import { describe, expect, it } from 'vitest';

import { buildCommunityListUrl, buildCommunityPostUrl } from './community-url';

describe('community URL helpers', () => {
  it('builds the canonical list URL without a default channel query', () => {
    expect(buildCommunityListUrl()).toBe('/apps/community');
    expect(buildCommunityListUrl('suggestions')).toBe('/apps/community');
  });

  it('preserves non-default channel context on list URLs', () => {
    expect(buildCommunityListUrl('team-news')).toBe(
      '/apps/community?channel=team-news',
    );
  });

  it('builds shareable post URLs', () => {
    expect(buildCommunityPostUrl('post-1')).toBe(
      '/apps/community/posts/post-1',
    );
    expect(buildCommunityPostUrl('post 1', 'questions')).toBe(
      '/apps/community/posts/post%201?channel=questions',
    );
  });
});
