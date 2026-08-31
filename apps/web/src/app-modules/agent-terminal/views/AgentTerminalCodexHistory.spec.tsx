import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AgentTerminalCodexThread } from '../api/agent-terminal-api';
import { AgentTerminalCodexHistory } from './AgentTerminalCodexHistory';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en-US' },
    t: (key: string, values?: Record<string, unknown>) =>
      values?.name ? `${key}:${values.name}` : key,
  }),
}));

const thread: AgentTerminalCodexThread = {
  created_at: '2026-08-27T01:00:00Z',
  id: '11111111-1111-1111-1111-111111111111',
  name: null,
  preview: 'Implement a clearer Codex resume history title',
  root_key: 'open-work-hub',
  root_path: '/home/user/projects/open-work-hub',
  updated_at: '2026-08-27T02:00:00Z',
};

describe('AgentTerminalCodexHistory', () => {
  it('shows Codex thread metadata and resumes the selected thread', () => {
    const onResume = vi.fn();

    render(
      <AgentTerminalCodexHistory
        disabled={false}
        failed={false}
        loading={false}
        onResume={onResume}
        onRetry={vi.fn()}
        resumingThreadId={null}
        threads={[thread]}
      />,
    );

    expect(
      screen.getByText('Implement a clearer Codex resume history title'),
    ).toBeTruthy();
    expect(screen.getByText(/open-work-hub/)).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', {
        name: 'agentTerminal.actions.resumeThreadLabel:Implement a clearer Codex resume history title',
      }),
    );

    expect(onResume).toHaveBeenCalledWith(thread);
  });

  it('keeps resume disabled when the terminal session limit is reached', () => {
    const onResume = vi.fn();

    render(
      <AgentTerminalCodexHistory
        disabled
        failed={false}
        loading={false}
        onResume={onResume}
        onRetry={vi.fn()}
        resumingThreadId={null}
        threads={[thread]}
      />,
    );

    const button = screen.getByRole('button', {
      name: 'agentTerminal.actions.resumeThreadLabel:Implement a clearer Codex resume history title',
    });
    expect(button.hasAttribute('disabled')).toBe(true);
    fireEvent.click(button);
    expect(onResume).not.toHaveBeenCalled();
  });
});
