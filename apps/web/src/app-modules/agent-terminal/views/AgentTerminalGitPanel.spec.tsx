import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getAgentTerminalGitCommit,
  getAgentTerminalGitCommitDiff,
  getAgentTerminalGitDiff,
  getAgentTerminalGitHistory,
  getAgentTerminalGitStatus,
  getAgentTerminalGitSummary,
} from '../api/agent-terminal-api';
import { AgentTerminalGitPanel } from './AgentTerminalGitPanel';

const feedbackApi = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
const diffSurfaceSpy = vi.hoisted(() => vi.fn());
const translate = vi.hoisted(
  () => (key: string, values?: Record<string, unknown>) =>
    values?.count === undefined ? key : `${key}:${values.count}`,
);
const COMMIT_SHA = '1234567890abcdef1234567890abcdef12345678';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: translate,
  }),
}));

vi.mock('@open-work-hub/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@open-work-hub/ui')>()),
  useFeedback: () => feedbackApi,
}));

vi.mock('../api/agent-terminal-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/agent-terminal-api')>()),
  getAgentTerminalGitCommit: vi.fn(),
  getAgentTerminalGitCommitDiff: vi.fn(),
  getAgentTerminalGitDiff: vi.fn(),
  getAgentTerminalGitHistory: vi.fn(),
  getAgentTerminalGitStatus: vi.fn(),
  getAgentTerminalGitSummary: vi.fn(),
}));

vi.mock('@/src/components/date/UserDateTime', () => ({
  UserDateTime: ({ value }: { value: string }) => <time>{value}</time>,
}));

vi.mock('./AgentTerminalDiffSurface', () => ({
  AgentTerminalDiffSurface: (props: Record<string, unknown>) => {
    diffSurfaceSpy(props);
    return (
      <div data-testid="agent-terminal-diff">{String(props.filePath)}</div>
    );
  },
}));

describe('AgentTerminalGitPanel', () => {
  beforeEach(() => {
    feedbackApi.error.mockReset();
    feedbackApi.success.mockReset();
    diffSurfaceSpy.mockReset();
    vi.mocked(getAgentTerminalGitStatus).mockResolvedValue({
      ahead: 1,
      behind: 0,
      branch: 'dev',
      changes: [
        {
          kind: 'modified',
          old_path: null,
          path: 'src/app.ts',
          scope: 'staged',
        },
        {
          kind: 'untracked',
          old_path: null,
          path: 'notes/new file.txt',
          scope: 'untracked',
        },
      ],
      head: '0123456789abcdef',
      is_repository: true,
      truncated: false,
      upstream: 'origin/dev',
    });
    vi.mocked(getAgentTerminalGitSummary).mockResolvedValue({
      is_repository: true,
      refs: [
        {
          current: true,
          full_name: 'refs/heads/dev',
          kind: 'local_branch',
          name: 'dev',
          target: COMMIT_SHA,
        },
        {
          current: false,
          full_name: 'refs/heads/feature/read-only',
          kind: 'local_branch',
          name: 'feature/read-only',
          target: 'abcdefabcdefabcdefabcdefabcdefabcdefabcd',
        },
        {
          current: false,
          full_name: 'refs/tags/v1.0.0',
          kind: 'tag',
          name: 'v1.0.0',
          target: COMMIT_SHA,
        },
      ],
      refs_truncated: false,
      stashes: [],
      stashes_truncated: false,
    });
    vi.mocked(getAgentTerminalGitHistory).mockResolvedValue({
      has_more: false,
      items: [
        {
          author_name: 'Test Author',
          authored_at: '2026-08-27T02:00:00Z',
          parents: [],
          sha: COMMIT_SHA,
          subject: 'initial commit',
        },
      ],
      offset: 0,
    });
    vi.mocked(getAgentTerminalGitCommit).mockResolvedValue({
      author_name: 'Test Author',
      authored_at: '2026-08-27T02:00:00Z',
      files: [
        {
          kind: 'added',
          old_path: null,
          path: 'src/initial.ts',
        },
        {
          kind: 'modified',
          old_path: null,
          path: 'docs/guide.md',
        },
      ],
      files_truncated: false,
      parents: [],
      sha: COMMIT_SHA,
      subject: 'initial commit',
    });
    vi.mocked(getAgentTerminalGitCommitDiff).mockImplementation(
      async (_token, _rootKey, commit, path) => ({
        commit,
        is_binary: false,
        kind: path === 'src/initial.ts' ? 'added' : 'modified',
        new_content:
          path === 'src/initial.ts' ? 'initial source\n' : 'updated guide\n',
        old_content: path === 'src/initial.ts' ? '' : 'old guide\n',
        old_path: null,
        path,
        too_large: false,
      }),
    );
    vi.mocked(getAgentTerminalGitDiff).mockImplementation(
      async (_token, _rootKey, change) => ({
        is_binary: false,
        kind: change.scope === 'untracked' ? 'untracked' : 'modified',
        new_content:
          change.scope === 'untracked' ? 'new note\n' : 'changed source\n',
        old_content: change.scope === 'untracked' ? '' : 'original source\n',
        old_path: null,
        path: change.path,
        scope: change.scope,
        too_large: false,
      }),
    );
  });

  it('loads the configured root and renders the selected file diff', async () => {
    render(<AgentTerminalGitPanel rootKey="project-root" token="token-1" />);

    expect(getAgentTerminalGitStatus).toHaveBeenCalledWith(
      'token-1',
      'project-root',
    );
    expect((await screen.findByTestId('agent-terminal-diff')).textContent).toBe(
      'src/app.ts',
    );
    expect(getAgentTerminalGitDiff).toHaveBeenCalledWith(
      'token-1',
      'project-root',
      expect.objectContaining({ path: 'src/app.ts', scope: 'staged' }),
    );

    fireEvent.click(screen.getByTitle('notes/new file.txt'));

    await waitFor(() =>
      expect(diffSurfaceSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({
          filePath: 'notes/new file.txt',
          newContent: 'new note\n',
          oldContent: '',
        }),
      ),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'agentTerminal.git.actions.expandDiff',
      }),
    );
    expect(await screen.findByRole('dialog')).toBeTruthy();
  });

  it('opens a focused commit file inspector and returns to read-only history', async () => {
    render(<AgentTerminalGitPanel rootKey="project-root" token="token-1" />);

    fireEvent.click(await screen.findByTitle(`${COMMIT_SHA} · initial commit`));

    await waitFor(() =>
      expect(getAgentTerminalGitCommitDiff).toHaveBeenCalledWith(
        'token-1',
        'project-root',
        COMMIT_SHA,
        'src/initial.ts',
      ),
    );
    expect(diffSurfaceSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({
        filePath: 'src/initial.ts',
        newContent: 'initial source\n',
      }),
    );
    expect(screen.queryByRole('button', { name: /initial commit/ })).toBeNull();
    expect(
      screen.getByRole('button', {
        name: 'agentTerminal.git.actions.backToHistory',
      }),
    ).toBeTruthy();

    fireEvent.click(screen.getByTitle('docs/guide.md'));
    await waitFor(() =>
      expect(diffSurfaceSpy).toHaveBeenLastCalledWith(
        expect.objectContaining({
          filePath: 'docs/guide.md',
          newContent: 'updated guide\n',
          oldContent: 'old guide\n',
        }),
      ),
    );

    fireEvent.click(
      screen.getByRole('button', {
        name: 'agentTerminal.git.actions.backToHistory',
      }),
    );
    expect(screen.getByRole('button', { name: /initial commit/ })).toBeTruthy();

    const changesSection = screen.getByRole('button', {
      name: 'agentTerminal.git.sections.changes 2',
    });
    fireEvent.click(changesSection);
    expect(screen.queryByTitle('src/app.ts')).toBeNull();
    fireEvent.click(changesSection);
    expect(screen.getByTitle('src/app.ts')).toBeTruthy();

    fireEvent.click(
      screen.getByRole('button', {
        name: 'agentTerminal.git.sections.branches 2',
      }),
    );
    const otherBranch = screen.getByText('feature/read-only');
    expect(otherBranch.closest('button')).toBeNull();
  });
});
