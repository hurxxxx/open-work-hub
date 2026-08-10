import type { AdminUsersQuery } from './admin-api';

export const USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE = 8;

export function buildUsageExcludedCandidateQuery({
  page,
  query,
}: {
  page: number;
  query: string;
}): AdminUsersQuery {
  const trimmedQuery = query.trim();
  return {
    page,
    page_size: USAGE_EXCLUDED_CANDIDATE_PAGE_SIZE,
    ...(trimmedQuery ? { q: trimmedQuery } : {}),
  };
}
