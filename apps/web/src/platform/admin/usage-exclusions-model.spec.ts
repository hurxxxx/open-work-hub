import { describe, expect, it } from 'vitest';

import {
  buildUsageExcludedCandidateQuery,
  USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
} from './usage-exclusions-model';

describe('usage exclusions model', () => {
  it('builds paged all-employee candidate searches', () => {
    expect(
      buildUsageExcludedCandidateQuery({ page: 3, query: '  Ada  ' }),
    ).toEqual({
      page: 3,
      page_size: USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
      q: 'Ada',
    });
  });

  it('omits empty search text while preserving pagination', () => {
    expect(buildUsageExcludedCandidateQuery({ page: 2, query: '   ' })).toEqual(
      {
        page: 2,
        page_size: USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
      },
    );
  });
});
