import { afterEach, describe, expect, it, vi } from 'vitest';

import { listAllPmsTaskLists, listPmsTaskLists } from './pms-api';

function response(items: Array<{ id: string }>, total = items.length) {
  return new Response(
    JSON.stringify({ items, total, page: 1, page_size: 100 }),
    {
      headers: { 'Content-Type': 'application/json' },
      status: 200,
    },
  );
}

describe('PMS task-list queries', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('requests active lists by default and supports archived-only queries', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(response([]));

    await listPmsTaskLists('token', 'space-1', 'workspace');
    await listPmsTaskLists('token', 'space-1', 'workspace', {
      archived: true,
    });

    expect(String(fetchSpy.mock.calls[0][0])).toContain('archived=false');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('archived=true');
  });

  it('preserves the archive filter while loading every page', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response([{ id: 'archived-1' }], 2))
      .mockResolvedValueOnce(response([{ id: 'archived-2' }], 2));

    const result = await listAllPmsTaskLists('token', undefined, 'workspace', {
      archived: true,
    });

    expect(result.items.map((item) => item.id)).toEqual([
      'archived-1',
      'archived-2',
    ]);
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(String(fetchSpy.mock.calls[0][0])).toContain('archived=true');
    expect(String(fetchSpy.mock.calls[1][0])).toContain('archived=true');
  });
});
