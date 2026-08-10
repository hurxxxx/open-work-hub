import { describe, expect, it } from 'vitest';

import {
  applyTaskDetailMentionPick,
  buildTaskCommentBodyBlocks,
  getTaskDetailMentionCandidates,
  getTaskDetailMentionState,
} from './useTaskDetailComments';

describe('task detail comment mention helpers', () => {
  it('opens mention suggestions after a trailing at sign', () => {
    expect(getTaskDetailMentionState('Please check @')).toEqual({
      mentionOpen: true,
      mentionQuery: '',
    });
  });

  it('tracks a lower-case mention query until whitespace appears', () => {
    expect(getTaskDetailMentionState('Please check @Al')).toEqual({
      mentionOpen: true,
      mentionQuery: 'al',
    });
    expect(getTaskDetailMentionState('Please check @Al now')).toEqual({
      mentionOpen: false,
      mentionQuery: '',
    });
  });

  it('filters mention candidates by full name', () => {
    expect(
      getTaskDetailMentionCandidates(
        [
          { email: 'alice@example.com', full_name: 'Alice Lee' },
          { email: 'bob@example.com', full_name: 'Bob Park' },
        ],
        'ali',
      ),
    ).toEqual([{ email: 'alice@example.com', full_name: 'Alice Lee' }]);
  });

  it('replaces the current mention token with the picked display label', () => {
    expect(
      applyTaskDetailMentionPick('Please check @ali', 'Alice Lee - Design'),
    ).toBe('Please check @Alice Lee - Design ');
  });

  it('builds mention body blocks using user ids and display labels', () => {
    expect(
      buildTaskCommentBodyBlocks('Please check @Alice Lee - Design', [
        { userId: 'user-1', displayName: 'Alice Lee - Design' },
      ]),
    ).toEqual([
      {
        type: 'paragraph',
        content: [
          { type: 'text', text: 'Please check ', styles: {} },
          {
            type: 'mention',
            props: {
              userId: 'user-1',
              displayName: 'Alice Lee - Design',
            },
          },
        ],
      },
    ]);
  });

  it('returns no body blocks when mention labels are no longer present', () => {
    expect(
      buildTaskCommentBodyBlocks('Please check Alice Lee', [
        { userId: 'user-1', displayName: 'Alice Lee' },
      ]),
    ).toBeNull();
  });
});
