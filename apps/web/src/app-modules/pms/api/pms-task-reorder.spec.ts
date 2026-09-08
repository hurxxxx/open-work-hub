import { afterEach, describe, expect, it, vi } from 'vitest';

import { reorderTaskListTasks } from './pms-api';

describe('PMS task reorder', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses the explicitly selected task list and one batch request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    );

    await reorderTaskListTasks('token', 'list-1', {
      items: [
        {
          board_position: 1000,
          parent_id: null,
          task_id: 'task-1',
        },
      ],
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0]?.[0]).toBe(
      '/api/v1/pms/lists/list-1/tasks/reorder',
    );
    expect(fetchSpy.mock.calls[0]?.[1]).toMatchObject({ method: 'PATCH' });
  });
});
