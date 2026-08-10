import { describe, expect, it } from 'vitest';

import {
  resolveSelectedAssigneeIds,
  resolveTaskDetailMemberNames,
} from './useTaskDetailIssueEditing';

describe('useTaskDetailIssueEditing model helpers', () => {
  it('prefers multi-assignee ids over the legacy single assignee id', () => {
    expect(
      resolveSelectedAssigneeIds({
        assignee_id: 'legacy-user',
        assignee_ids: ['user-1', 'user-2'],
      }),
    ).toEqual(['user-1', 'user-2']);
  });

  it('falls back to the legacy single assignee id when no assignee ids exist', () => {
    expect(
      resolveSelectedAssigneeIds({
        assignee_id: 'legacy-user',
        assignee_ids: [],
      }),
    ).toEqual(['legacy-user']);
  });

  it('resolves member names with fallback names before raw user ids', () => {
    expect(
      resolveTaskDetailMemberNames(
        [{ full_name: 'Known Member', user_id: 'user-1' }],
        ['user-1', 'user-2', 'user-3'],
        ['Ignored Fallback', 'Fallback Member'],
      ),
    ).toEqual(['Known Member', 'Fallback Member', 'user-3']);
  });
});
