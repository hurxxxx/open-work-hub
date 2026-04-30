import type { IssueFilterParams, PmsIssue } from './pms-api';

export const DEFAULT_ISSUE_ARCHIVED_STATE = 'active' as const;

export function createDefaultIssueFilterParams(
  overrides: Partial<IssueFilterParams> = {},
): IssueFilterParams {
  return {
    archived_state: DEFAULT_ISSUE_ARCHIVED_STATE,
    ...overrides,
  };
}

export function reconcileSelectedIssueIds(
  selectedIds: Set<string>,
  issues: Array<Pick<PmsIssue, 'id'>>,
): Set<string> {
  if (selectedIds.size === 0) {
    return selectedIds;
  }

  const visibleIds = new Set(issues.map((issue) => issue.id));
  return new Set(Array.from(selectedIds).filter((id) => visibleIds.has(id)));
}

export function toLocalDateInputValue(value: Date = new Date()): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}
