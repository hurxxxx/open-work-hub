import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { RecentPageItem } from '@/src/app-modules/docs/public-api';
import type { MeetingListItem } from '@/src/app-modules/meeting/public-api';
import type { PlannerEvent } from '@/src/app-modules/planner/public-api';
import type { PmsTask } from '@/src/app-modules/pms/public-api';
import { useHomeController, type HomeClient } from './useHomeController';

describe('useHomeController', () => {
  it('loads home meetings, assigned tasks, and recent pages through the client', async () => {
    const client = clientWith({
      listAssignedTasks: vi.fn().mockResolvedValue({ items: [task('task-1')] }),
      listMeetings: vi
        .fn()
        .mockResolvedValue({ items: [meeting('meeting-1')] }),
      listPlannerEvents: vi
        .fn()
        .mockResolvedValue({ items: [event('event-1')] }),
      listRecentPages: vi.fn().mockResolvedValue([page('page-1')]),
    });
    const { result } = renderController({ client });

    await waitFor(() => {
      expect(result.current.state.meetings).toHaveLength(1);
      expect(result.current.state.issues).toHaveLength(1);
      expect(result.current.state.recentPages).toHaveLength(1);
      expect(result.current.state.plannerEvents).toHaveLength(1);
    });
    expect(result.current.state.meetingsLoading).toBe(false);
    expect(result.current.state.issuesLoading).toBe(false);
    expect(result.current.state.pagesLoading).toBe(false);
    expect(result.current.state.plannerLoading).toBe(false);
    expect(client.listMeetings).toHaveBeenCalledWith('token', {
      scope: 'upcoming',
    });
    expect(client.listAssignedTasks).toHaveBeenCalledWith('token', {
      limit: 10,
    });
    expect(client.listRecentPages).toHaveBeenCalledWith('token', 10);
    expect(client.listPlannerEvents).toHaveBeenCalledWith(
      'token',
      expect.objectContaining({
        from: expect.any(String),
        to: expect.any(String),
      }),
    );
  });

  it('tracks each failed source independently', async () => {
    const client = clientWith({
      listAssignedTasks: vi.fn().mockRejectedValue(new Error('tasks failed')),
      listMeetings: vi
        .fn()
        .mockResolvedValue({ items: [meeting('meeting-1')] }),
      listRecentPages: vi.fn().mockRejectedValue(new Error('pages failed')),
    });
    const { result } = renderController({ client });

    await waitFor(() => {
      expect(result.current.state.meetingsLoading).toBe(false);
      expect(result.current.state.issuesLoading).toBe(false);
      expect(result.current.state.pagesLoading).toBe(false);
    });
    expect(result.current.state.meetings).toHaveLength(1);
    expect(result.current.state.issues).toEqual([]);
    expect(result.current.state.recentPages).toEqual([]);
  });

  it('does not load without token or workspace slug', () => {
    const client = clientWith();
    renderController({ client, token: null });

    expect(client.listMeetings).not.toHaveBeenCalled();
    expect(client.listAssignedTasks).not.toHaveBeenCalled();
    expect(client.listRecentPages).not.toHaveBeenCalled();
    expect(client.listPlannerEvents).not.toHaveBeenCalled();
  });

  it('does not request data from disabled workspace apps', async () => {
    const client = clientWith();
    const { result } = renderController({
      client,
      enabledAppIds: ['docs', 'planner', 'pms'],
    });

    await waitFor(() => {
      expect(result.current.state.meetingsLoading).toBe(false);
      expect(result.current.state.issuesLoading).toBe(false);
      expect(result.current.state.pagesLoading).toBe(false);
      expect(result.current.state.plannerLoading).toBe(false);
    });
    expect(client.listMeetings).not.toHaveBeenCalled();
    expect(client.listAssignedTasks).toHaveBeenCalled();
    expect(client.listRecentPages).toHaveBeenCalled();
    expect(client.listPlannerEvents).toHaveBeenCalled();
  });

  it('waits for workspace bootstrap before loading home data', () => {
    const client = clientWith();
    renderController({ client, enabledAppIds: null });

    expect(client.listMeetings).not.toHaveBeenCalled();
    expect(client.listAssignedTasks).not.toHaveBeenCalled();
    expect(client.listRecentPages).not.toHaveBeenCalled();
    expect(client.listPlannerEvents).not.toHaveBeenCalled();
  });
});

function renderController(
  options: {
    client?: HomeClient;
    enabledAppIds?: readonly string[] | null;
    timeZone?: string;
    token?: string | null;
  } = {},
) {
  const enabledAppIds =
    options.enabledAppIds === undefined
      ? ['docs', 'meeting', 'planner', 'pms']
      : options.enabledAppIds;
  return renderHook(() =>
    useHomeController({
      client: options.client ?? clientWith(),
      enabledAppIds,
      timeZone: options.timeZone ?? 'UTC',
      token: options.token === undefined ? 'token' : options.token,
    }),
  );
}

function clientWith(overrides: Partial<HomeClient> = {}): HomeClient {
  return {
    listAssignedTasks: vi.fn().mockResolvedValue({ items: [] }),
    listMeetings: vi.fn().mockResolvedValue({ items: [] }),
    listPlannerEvents: vi.fn().mockResolvedValue({ items: [] }),
    listRecentPages: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
}

function meeting(id: string): MeetingListItem {
  return {
    id,
    start_at: '2026-05-20T00:00:00.000Z',
    title: id,
  } as MeetingListItem;
}

function task(id: string): PmsTask {
  return {
    due_date: null,
    id,
    priority: 'low',
    title: id,
  } as PmsTask;
}

function page(id: string): RecentPageItem {
  return {
    doc_id: `doc-${id}`,
    doc_title: id,
    page_id: id,
    page_title: id,
  } as RecentPageItem;
}

function event(id: string): PlannerEvent {
  return {
    id,
    title: id,
    allDay: false,
    start: '2026-06-15T01:00:00.000Z',
    end: '2026-06-15T02:00:00.000Z',
  } as PlannerEvent;
}
