import { describe, expect, it } from 'vitest';

import type { PmsTaskListMember } from '../api/pms-api';
import { getTaskCommentBodySegments } from './TaskDetailActivityPanel';

function member(
  overrides: Partial<PmsTaskListMember> = {},
): PmsTaskListMember {
  return {
    user_id: 'user-1',
    email: 'member@example.test',
    full_name: 'Member One',
    primary_org_unit_name: 'Product',
    is_admin: false,
    role: 'member',
    joined_at: '2026-06-10T00:00:00.000Z',
    ...overrides,
  };
}

describe('TaskDetailActivityPanel comment body rendering', () => {
  it('renders a mention-only block without a leading text segment', () => {
    expect(
      getTaskCommentBodySegments(
        '@Member One - Product',
        [
          {
            type: 'paragraph',
            content: [
              {
                type: 'mention',
                props: {
                  userId: 'user-1',
                  displayName: 'Member One - Product',
                },
              },
            ],
          },
        ],
        [member()],
      ),
    ).toEqual([
      {
        type: 'mention',
        key: '0-0-user-1',
        userId: 'user-1',
        displayName: 'Member One - Product',
      },
    ]);
  });

  it('falls back to workspace member display labels for legacy id mentions', () => {
    expect(
      getTaskCommentBodySegments('@user-1', null, [
        member({ user_id: '00000000-0000-0000-0000-000000000001' }),
      ]),
    ).toEqual([{ type: 'text', text: '@user-1' }]);

    expect(
      getTaskCommentBodySegments(
        '@00000000-0000-0000-0000-000000000001',
        null,
        [member({ user_id: '00000000-0000-0000-0000-000000000001' })],
      ),
    ).toEqual([
      {
        type: 'mention',
        key: '1-00000000-0000-0000-0000-000000000001',
        userId: '00000000-0000-0000-0000-000000000001',
        displayName: 'Member One - Product',
      },
    ]);
  });
});
