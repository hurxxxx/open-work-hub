import type { BlockContent } from '@open-work-hub/ui';
import { describe, expect, it } from 'vitest';

import type { PmsTaskListStatus, PmsTaskTemplate } from '../api/pms-api';
import {
  applyNewTaskTemplate,
  buildNewTaskCreatePayload,
  createInitialNewTaskState,
  newTaskReducer,
  reconcileNewTaskDueDate,
  reconcileNewTaskStartDate,
  resolveNewTaskStatus,
} from './new-task-modal-model';

function taskListStatus(
  slug: string,
  category: PmsTaskListStatus['category'] = 'active',
): PmsTaskListStatus {
  return {
    id: `status-${slug}`,
    name: slug,
    slug,
    category,
    sort_order: 0,
    color: '#94a3b8',
  };
}

function taskTemplate(
  overrides: Partial<PmsTaskTemplate> = {},
): PmsTaskTemplate {
  return {
    id: 'template-1',
    name: 'Template task',
    description: null,
    default_status: 'todo',
    default_priority: 'medium',
    checklist_items: null,
    ...overrides,
  } as PmsTaskTemplate;
}

const taskListStatuses: PmsTaskListStatus[] = [
  taskListStatus('draft', 'not_started'),
  taskListStatus('doing', 'active'),
  taskListStatus('done', 'done'),
];

const descriptionBlocks: BlockContent = [
  {
    id: 'block-1',
    type: 'paragraph',
    props: {
      backgroundColor: 'default',
      textColor: 'default',
      textAlignment: 'left',
    },
    content: [{ type: 'text', text: 'Keep this', styles: {} }],
    children: [],
  },
];

describe('new task modal model', () => {
  it('creates the initial draft from the task list default status', () => {
    expect(createInitialNewTaskState(taskListStatuses)).toMatchObject({
      title: '',
      parentId: null,
      status: 'doing',
      priority: 'medium',
      startDate: '',
      dueDate: '',
      assignToMe: false,
      showDescription: false,
      descriptionBlocks: undefined,
      submitting: false,
      templates: [],
      templateMenuOpen: false,
      error: null,
    });
    expect(createInitialNewTaskState().status).toBe('todo');
    expect(
      createInitialNewTaskState(taskListStatuses, '  Follow up  ').title,
    ).toBe('Follow up');
  });

  it('reconciles start and due date edits without clearing unrelated dates', () => {
    expect(reconcileNewTaskStartDate('2026-06-10', '2026-06-01')).toEqual({
      startDate: '2026-06-10',
      dueDate: '2026-06-10',
    });
    expect(reconcileNewTaskStartDate('2026-06-01', '2026-06-10')).toEqual({
      startDate: '2026-06-01',
      dueDate: '2026-06-10',
    });
    expect(reconcileNewTaskDueDate('2026-06-10', '2026-06-01')).toEqual({
      startDate: '2026-06-01',
      dueDate: '2026-06-01',
    });
    expect(reconcileNewTaskDueDate('2026-06-10', '')).toEqual({
      startDate: '2026-06-10',
      dueDate: '',
    });
  });

  it('applies templates while preserving existing description blocks', () => {
    const state = {
      ...createInitialNewTaskState(taskListStatuses),
      descriptionBlocks,
      templateMenuOpen: true,
    };

    const applied = applyNewTaskTemplate(
      state,
      taskTemplate({
        name: 'Release checklist',
        description: 'Seed description',
        default_status: 'backlog',
        default_priority: 'high',
      }),
      taskListStatuses,
    );

    expect(applied).toMatchObject({
      title: 'Release checklist',
      status: 'doing',
      priority: 'high',
      showDescription: true,
      templateMenuOpen: false,
    });
    expect(applied.descriptionBlocks).toBe(descriptionBlocks);

    expect(
      applyNewTaskTemplate(
        state,
        taskTemplate({ default_status: 'removed-status' }),
        taskListStatuses,
      ).status,
    ).toBe('doing');
  });

  it('builds create payloads with normalized title, dates, and status', () => {
    const state = {
      ...createInitialNewTaskState(taskListStatuses),
      title: '  Ship task  ',
      status: 'removed-status',
      priority: 'critical',
      parentId: 'parent-task-1',
      startDate: '',
      dueDate: '2026-06-30',
      descriptionBlocks,
    };

    expect(buildNewTaskCreatePayload(state, taskListStatuses)).toEqual({
      title: 'Ship task',
      description: '',
      description_blocks: descriptionBlocks,
      status: 'doing',
      priority: 'critical',
      assignee_id: null,
      milestone_id: null,
      parent_id: 'parent-task-1',
      start_date: null,
      due_date: '2026-06-30',
    });
    expect(
      buildNewTaskCreatePayload(
        { ...state, assignToMe: true },
        taskListStatuses,
        { assignToUserId: 'user-1' },
      ).assignee_id,
    ).toBe('user-1');
    expect(
      buildNewTaskCreatePayload({ ...state, parentId: null }, taskListStatuses)
        .parent_id,
    ).toBeNull();
    expect(
      buildNewTaskCreatePayload(
        { ...state, assignToMe: false },
        taskListStatuses,
        { assignToUserId: 'user-1' },
      ).assignee_id,
    ).toBeNull();
    expect(
      buildNewTaskCreatePayload(
        { ...state, status: 'backlog' },
        taskListStatuses,
      ).status,
    ).toBe('doing');
    expect(
      buildNewTaskCreatePayload({ ...state, descriptionBlocks: undefined })
        .description_blocks,
    ).toBeNull();
  });

  it('keeps reducer transitions pure and delegates template policy', () => {
    const state = createInitialNewTaskState(taskListStatuses);

    expect(
      newTaskReducer(state, {
        type: 'assign-to-me',
        value: true,
      }),
    ).toMatchObject({ assignToMe: true });

    expect(
      newTaskReducer(state, {
        type: 'parent-id',
        value: 'parent-1',
      }),
    ).toMatchObject({ parentId: 'parent-1' });

    expect(
      newTaskReducer(state, {
        type: 'start-date',
        value: '2026-07-01',
      }),
    ).toMatchObject({ startDate: '2026-07-01', dueDate: '' });

    expect(
      newTaskReducer(
        {
          ...state,
          templateMenuOpen: true,
        },
        {
          type: 'apply-template',
          taskListStatuses,
          template: taskTemplate({ default_status: 'backlog' }),
        },
      ),
    ).toMatchObject({
      status: 'doing',
      templateMenuOpen: false,
    });
  });

  it('resolves backlog and invalid statuses to the default list status', () => {
    expect(resolveNewTaskStatus('backlog', taskListStatuses)).toBe('doing');
    expect(resolveNewTaskStatus('removed-status', taskListStatuses)).toBe(
      'doing',
    );
    expect(resolveNewTaskStatus('doing', taskListStatuses)).toBe('doing');
    expect(resolveNewTaskStatus('custom-without-list')).toBe(
      'custom-without-list',
    );
  });
});
