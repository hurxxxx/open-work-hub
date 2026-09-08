import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createChecklistItem,
  createTaskComment,
  createTaskListTask,
  deleteAttachment,
  deleteChecklistItem,
  deleteTask,
  getTaskDetail,
  listTaskActivityLogs,
  setTaskAssignees,
  setTaskFollowers,
  updateChecklistItem,
  updateTask,
  uploadAttachment,
} from './pms-api';

describe('PMS task-detail API boundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('routes every detail read and mutation through the PMS API', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ items: [] }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      ),
    );

    await getTaskDetail('token', 'task-1');
    await listTaskActivityLogs('token', 'task-1');
    await updateTask('token', 'task-1', { title: 'Updated' });
    await setTaskAssignees('token', 'task-1', ['user-1']);
    await setTaskFollowers('token', 'task-1', ['user-2']);
    await createTaskListTask('token', 'list-1', {
      assignee_id: null,
      description: '',
      due_date: null,
      milestone_id: null,
      priority: 'medium',
      status: 'todo',
      title: 'Subtask',
    });
    await deleteTask('token', 'task-2');
    await createChecklistItem('token', 'task-1', { text: 'Check' });
    await updateChecklistItem('token', 'check-1', { completed: true });
    await deleteChecklistItem('token', 'check-1');
    await uploadAttachment(
      'token',
      'task-1',
      new File(['content'], 'note.txt', { type: 'text/plain' }),
    );
    await deleteAttachment('token', 'attachment-1');
    await createTaskComment('token', 'task-1', 'Comment', null);

    expect(fetchSpy).toHaveBeenCalledTimes(13);
    for (const [input] of fetchSpy.mock.calls) {
      expect(String(input)).toMatch(/^\/api\/v1\/pms\//);
    }
  });
});
