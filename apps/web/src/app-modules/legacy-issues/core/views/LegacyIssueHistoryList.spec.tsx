import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LegacyIssueHistoryList } from './LegacyIssueHistoryList';

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    user: {
      date_format: 'iso',
      locale: 'ko-KR',
      time_zone: 'Asia/Seoul',
    },
  }),
}));

describe('LegacyIssueHistoryList', () => {
  it('formats history timestamps with the user timezone', () => {
    render(
      <LegacyIssueHistoryList
        loading={false}
        items={[
          {
            action: 'update',
            actor_email: 'user@example.com',
            actor_name: 'User',
            created_at: '2026-05-01T18:30:00Z',
            field_label: '발생 단계',
            id: 'history-1',
            new_value: 'P2',
            old_value: 'P1',
          },
        ]}
      />,
    );

    expect(screen.getByText('2026-05-02 03:30')).not.toBeNull();
  });
});
