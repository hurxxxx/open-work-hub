import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { TaskDetail } from './TaskDetail';
import type { PmsIssue } from '@/src/domains/pms/pms-api';

const mockGetIssueDetail = vi.fn();
const mockListIssueActivityLogs = vi.fn();
const mockUpdateIssue = vi.fn();
const mockDeleteIssue = vi.fn();
const mockCreateIssueComment = vi.fn();
const mockCreateProjectIssue = vi.fn();

vi.mock('@aidoo/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Button: ({
    children,
    onClick,
    type = 'button',
    disabled,
  }: {
    children?: ReactNode;
    onClick?: () => void;
    type?: 'button' | 'submit' | 'reset';
    disabled?: boolean;
  }) => (
    <button disabled={disabled} onClick={onClick} type={type}>
      {children}
    </button>
  ),
  BlockEditor: () => <div data-testid="block-editor" />,
  BlockViewer: () => <div data-testid="block-viewer" />,
}));

vi.mock('@/src/domains/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'test-token',
  }),
}));

vi.mock('@/src/domains/pms/pms-api', () => ({
  getIssueDetail: (...args: unknown[]) => mockGetIssueDetail(...args),
  listIssueActivityLogs: (...args: unknown[]) => mockListIssueActivityLogs(...args),
  updateIssue: (...args: unknown[]) => mockUpdateIssue(...args),
  deleteIssue: (...args: unknown[]) => mockDeleteIssue(...args),
  createIssueComment: (...args: unknown[]) => mockCreateIssueComment(...args),
  createProjectIssue: (...args: unknown[]) => mockCreateProjectIssue(...args),
}));

function buildIssue(overrides: Partial<PmsIssue> = {}): PmsIssue {
  return {
    id: 'issue-1',
    project_id: 'project-1',
    reference: 'AID-1',
    title: 'Initial task',
    description: 'Initial description',
    description_blocks: null,
    parent_id: null,
    subtask_count: 0,
    status: 'todo',
    status_label: 'Todo',
    priority: 'medium',
    priority_label: 'Medium',
    assignee_id: null,
    assignee_name: null,
    reporter_id: 'user-1',
    reporter_name: 'Reporter',
    milestone_id: null,
    milestone_title: null,
    start_date: null,
    due_date: null,
    board_position: 1,
    archived: false,
    progress: 0,
    comments_count: 0,
    labels: [],
    updated_at: '2026-04-08T00:00:00Z',
    ...overrides,
  };
}

describe('TaskDetail', () => {
  beforeEach(() => {
    mockGetIssueDetail.mockResolvedValue({
      issue: buildIssue(),
      comments: [],
      dependencies: [],
      subtasks: [],
    });
    mockListIssueActivityLogs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    mockDeleteIssue.mockResolvedValue(undefined);
    mockCreateIssueComment.mockResolvedValue(undefined);
    mockCreateProjectIssue.mockResolvedValue(buildIssue({ id: 'issue-2', reference: 'AID-2' }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('keeps optimistic field changes visible while the parent refreshes', async () => {
    let resolveUpdate: ((value: PmsIssue) => void) | undefined;
    mockUpdateIssue.mockReturnValueOnce(
      new Promise<PmsIssue>((resolve) => {
        resolveUpdate = resolve;
      }),
    );
    const onUpdate = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();

    render(
      <TaskDetail
        issue={buildIssue()}
        members={[]}
        milestones={[]}
        projectLabels={[]}
        onClose={onClose}
        onUpdate={onUpdate}
      />,
    );

    await waitFor(() => {
      expect(mockGetIssueDetail).toHaveBeenCalled();
    });

    const [statusSelect] = screen.getAllByRole('combobox');
    fireEvent.change(statusSelect, { target: { value: 'done' } });

    expect((statusSelect as HTMLSelectElement).value).toBe('done');

    resolveUpdate?.(
      buildIssue({
        status: 'done',
        status_label: 'Done',
        progress: 1,
        updated_at: '2026-04-08T01:00:00Z',
      }),
    );

    await waitFor(() => {
      expect(onUpdate).toHaveBeenCalledTimes(1);
    });
    expect((statusSelect as HTMLSelectElement).value).toBe('done');
  });
});
