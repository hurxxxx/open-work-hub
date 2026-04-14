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
const mockCreateTaskListIssue = vi.fn();
const mockUploadAttachment = vi.fn();
const mockDeleteAttachment = vi.fn();
const mockCreateChecklistItem = vi.fn();
const mockUpdateChecklistItem = vi.fn();
const mockDeleteChecklistItem = vi.fn();
const mockCreateTimeEntry = vi.fn();
const mockDeleteTimeEntry = vi.fn();
const mockCreateDependency = vi.fn();
const mockDeleteDependency = vi.fn();
const mockListTaskListIssues = vi.fn();

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
  createTaskListIssue: (...args: unknown[]) => mockCreateTaskListIssue(...args),
  uploadAttachment: (...args: unknown[]) => mockUploadAttachment(...args),
  deleteAttachment: (...args: unknown[]) => mockDeleteAttachment(...args),
  createChecklistItem: (...args: unknown[]) => mockCreateChecklistItem(...args),
  updateChecklistItem: (...args: unknown[]) => mockUpdateChecklistItem(...args),
  deleteChecklistItem: (...args: unknown[]) => mockDeleteChecklistItem(...args),
  createTimeEntry: (...args: unknown[]) => mockCreateTimeEntry(...args),
  deleteTimeEntry: (...args: unknown[]) => mockDeleteTimeEntry(...args),
  createDependency: (...args: unknown[]) => mockCreateDependency(...args),
  deleteDependency: (...args: unknown[]) => mockDeleteDependency(...args),
  listTaskListIssues: (...args: unknown[]) => mockListTaskListIssues(...args),
}));

function buildIssue(overrides: Partial<PmsIssue> = {}): PmsIssue {
  return {
    id: 'issue-1',
    list_id: 'task-list-1',
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
    checklist_total: 0,
    checklist_done: 0,
    estimate_hours: null,
    time_spent_minutes: 0,
    recurrence_rule: null,
    assignee_ids: [],
    assignee_names: [],
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
      attachments: [],
      checklist_items: [],
      time_entries: [],
    });
    mockListIssueActivityLogs.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    mockDeleteIssue.mockResolvedValue(undefined);
    mockCreateIssueComment.mockResolvedValue(undefined);
    mockCreateTaskListIssue.mockResolvedValue(buildIssue({ id: 'issue-2', reference: 'AID-2' }));
    mockUploadAttachment.mockResolvedValue(undefined);
    mockDeleteAttachment.mockResolvedValue(undefined);
    mockCreateChecklistItem.mockResolvedValue(undefined);
    mockUpdateChecklistItem.mockResolvedValue(undefined);
    mockDeleteChecklistItem.mockResolvedValue(undefined);
    mockCreateTimeEntry.mockResolvedValue(undefined);
    mockDeleteTimeEntry.mockResolvedValue(undefined);
    mockCreateDependency.mockResolvedValue(undefined);
    mockDeleteDependency.mockResolvedValue(undefined);
    mockListTaskListIssues.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 });
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
        taskListLabels={[]}
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

  it('renders attachment links from presigned download urls', async () => {
    mockGetIssueDetail.mockResolvedValueOnce({
      issue: buildIssue(),
      comments: [],
      dependencies: [],
      subtasks: [],
      attachments: [
        {
          id: 'attachment-1',
          issue_id: 'issue-1',
          filename: 'spec-image.png',
          content_type: 'image/png',
          size_bytes: 2048,
          download_url: 'https://minio.example/spec-image.png?signature=test',
          uploaded_by_id: 'user-1',
          uploaded_by_name: 'Reporter',
          created_at: '2026-04-08T00:00:00Z',
        },
      ],
      checklist_items: [],
      time_entries: [],
    });

    render(
      <TaskDetail
        issue={buildIssue()}
        members={[]}
        milestones={[]}
        taskListLabels={[]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByAltText('spec-image.png').getAttribute('src'),
      ).toBe('https://minio.example/spec-image.png?signature=test');
    });

    expect(
      screen.getByRole('link', { name: 'spec-image.png 다운로드' }).getAttribute('href'),
    ).toBe('https://minio.example/spec-image.png?signature=test');
  });

  it('shows restore action for archived issues', async () => {
    render(
      <TaskDetail
        issue={buildIssue({ archived: true })}
        members={[]}
        milestones={[]}
        taskListLabels={[]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetIssueDetail).toHaveBeenCalled();
    });

    expect(screen.getByRole('button', { name: 'Restore' })).toBeTruthy();
    expect(screen.getByText('Archived')).toBeTruthy();
  });

  it('renders task detail in read-only mode when editing is disabled', async () => {
    render(
      <TaskDetail
        issue={buildIssue()}
        members={[]}
        milestones={[]}
        taskListLabels={[]}
        canEdit={false}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(mockGetIssueDetail).toHaveBeenCalled();
    });

    expect(screen.getByText('Read only')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Archive' })).toBeNull();
    expect(screen.getAllByRole('combobox')[0].hasAttribute('disabled')).toBe(true);
    expect(screen.getByPlaceholderText('Comments are read-only').hasAttribute('disabled')).toBe(true);
    expect(screen.queryByText('Click or drag files to upload')).toBeNull();
  });
});
