import { describe, expect, it } from 'vitest';
import type { RecentPageItem } from '@/src/app-modules/docs/public-api';
import type { MeetingListItem } from '@/src/app-modules/meeting/public-api';
import type { PlannerEvent } from '@/src/app-modules/planner/public-api';
import type { PmsTask } from '@/src/app-modules/pms/public-api';
import type { WorkspaceNotification } from '@/src/platform/notifications/notifications-api';
import {
  INITIAL_WORKSPACE_HOME_STATE,
  buildWorkspaceHomeSections,
  formatHomeDueDate,
  getHomeGreeting,
  selectTodayMeetings,
  selectTopAssignedTasks,
  selectTopRecentPages,
  workspaceHomePriorityTone,
  workspaceHomeReducer,
} from './workspace-home-model';

const t = (key: string, options?: Record<string, unknown>) =>
  typeof options?.count === 'number' ? `${key}:${options.count}` : key;

function meeting(id: string, startAt: string): MeetingListItem {
  return {
    id,
    title: `Meeting ${id}`,
    start_at: startAt,
  } as MeetingListItem;
}

function task(id: string, overrides: Partial<PmsTask> = {}): PmsTask {
  return {
    id,
    title: `Task ${id}`,
    due_date: null,
    priority: 'low',
    ...overrides,
  } as PmsTask;
}

function page(
  id: string,
  overrides: Partial<RecentPageItem> = {},
): RecentPageItem {
  return {
    page_id: id,
    page_title: `Page ${id}`,
    doc_id: `doc-${id}`,
    doc_title: `Doc ${id}`,
    ...overrides,
  } as RecentPageItem;
}

describe('workspace-home-model', () => {
  it('selects the greeting from the zoned hour', () => {
    expect(getHomeGreeting('UTC', t, new Date('2026-01-01T08:00:00Z'))).toBe(
      'home.greetingMorning',
    );
    expect(getHomeGreeting('UTC', t, new Date('2026-01-01T13:00:00Z'))).toBe(
      'home.greetingAfternoon',
    );
    expect(getHomeGreeting('UTC', t, new Date('2026-01-01T20:00:00Z'))).toBe(
      'home.greetingEvening',
    );
  });

  it('formats due date labels relative to the current zoned date', () => {
    const now = new Date('2026-01-10T03:00:00Z');

    expect(formatHomeDueDate('2026-01-10', 'UTC', 'en-US', t, now)).toBe(
      'home.dueToday',
    );
    expect(formatHomeDueDate('2026-01-11', 'UTC', 'en-US', t, now)).toBe(
      'home.dueTomorrow',
    );
    expect(formatHomeDueDate('2026-01-09', 'UTC', 'en-US', t, now)).toBe(
      'home.dueYesterday',
    );
    expect(formatHomeDueDate('2026-01-05', 'UTC', 'en-US', t, now)).toBe(
      'home.dueOverdue:5',
    );
    expect(formatHomeDueDate('not-a-date', 'UTC', 'en-US', t, now)).toBe('');
  });

  it('filters today meetings in timezone order and caps the list', () => {
    const meetings = [
      meeting('a', '2026-01-10T00:00:00Z'),
      meeting('b', '2026-01-10T01:00:00Z'),
      meeting('c', '2026-01-10T02:00:00Z'),
      meeting('d', '2026-01-10T03:00:00Z'),
      meeting('e', '2026-01-10T04:00:00Z'),
      meeting('f', '2026-01-10T05:00:00Z'),
      meeting('next-day', '2026-01-11T00:00:00Z'),
    ];

    expect(
      selectTodayMeetings(
        meetings,
        'UTC',
        new Date('2026-01-10T12:00:00Z'),
      ).map((item) => item.id),
    ).toEqual(['a', 'b', 'c', 'd', 'e']);
  });

  it('caps task and recent page summaries', () => {
    expect(
      selectTopAssignedTasks([1, 2, 3, 4, 5, 6].map(String).map(task)),
    ).toHaveLength(5);
    expect(
      selectTopRecentPages([1, 2, 3, 4, 5, 6].map(String).map(page)),
    ).toHaveLength(5);
  });

  it('maps task priorities to summary tones', () => {
    expect(workspaceHomePriorityTone('critical')).toBe('danger');
    expect(workspaceHomePriorityTone('high')).toBe('danger');
    expect(workspaceHomePriorityTone('medium')).toBe('warning');
    expect(workspaceHomePriorityTone('low')).toBe('muted');
    expect(workspaceHomePriorityTone(undefined)).toBe('muted');
  });

  it('builds loading, empty, and ready home summary sections', () => {
    expect(
      buildWorkspaceHomeSections({
        locale: 'en-US',
        now: new Date('2026-01-10T12:00:00Z'),
        state: INITIAL_WORKSPACE_HOME_STATE,
        timeZone: 'UTC',
        t,
        workspaceSlug: 'team alpha',
      }).map((section) => [section.id, section.status, section.actionTo]),
    ).toEqual([
      ['planner', 'loading', '/apps/planner'],
      ['meetings', 'loading', '/apps/meeting/workspaces/team%20alpha'],
      ['tasks', 'loading', '/apps/pms/workspaces/team%20alpha/assigned'],
      ['docs', 'loading', '/apps/docs/workspaces/team%20alpha'],
      ['notifications', 'loading', ''],
    ]);

    expect(
      buildWorkspaceHomeSections({
        locale: 'en-US',
        now: new Date('2026-01-10T12:00:00Z'),
        state: {
          meetings: [],
          meetingsLoading: false,
          issues: [],
          issuesLoading: false,
          recentPages: [],
          pagesLoading: false,
          plannerEvents: [],
          plannerLoading: false,
          notifications: [],
          notificationsLoading: false,
        },
        timeZone: 'UTC',
        t,
        workspaceSlug: 'team alpha',
      }).map((section) => [section.id, section.status]),
    ).toEqual([
      ['planner', 'empty'],
      ['meetings', 'empty'],
      ['tasks', 'empty'],
      ['docs', 'empty'],
      ['notifications', 'empty'],
    ]);
  });

  it('projects loaded meetings, tasks, and docs into stable rows', () => {
    const sections = buildWorkspaceHomeSections({
      locale: 'en-US',
      now: new Date('2026-01-10T12:00:00Z'),
      state: {
        meetings: [
          meeting('today', '2026-01-10T09:00:00Z'),
          meeting('tomorrow', '2026-01-11T09:00:00Z'),
        ],
        meetingsLoading: false,
        issues: [
          task('due', {
            due_date: '2026-01-11',
            priority: 'high',
          }),
        ],
        issuesLoading: false,
        recentPages: [
          page('page-1', {
            page_title: '',
            doc_id: 'doc-1',
            doc_title: 'Project Notes',
          }),
        ],
        pagesLoading: false,
        plannerEvents: [],
        plannerLoading: false,
        notifications: [],
        notificationsLoading: false,
      },
      timeZone: 'UTC',
      t,
      workspaceSlug: 'team alpha',
    });

    expect(sections[1]?.rows).toMatchObject([
      {
        kind: 'meeting',
        id: 'today',
        title: 'Meeting today',
        to: '/apps/meeting/workspaces/team%20alpha/meetings/today',
      },
    ]);
    expect(sections[2]?.rows).toEqual([
      {
        kind: 'task',
        id: 'due',
        title: 'Task due',
        to: '/apps/pms/workspaces/team%20alpha/assigned?task=due',
        trailing: 'home.dueTomorrow',
        priorityTone: 'danger',
      },
    ]);
    expect(sections[3]?.rows).toEqual([
      {
        kind: 'doc',
        id: 'page-1',
        title: 'home.untitled',
        subtitle: 'Project Notes',
        to: '/apps/docs/workspaces/team%20alpha/documents/doc-1',
      },
    ]);
  });

  it('orders upcoming planner events by start and links to the planner app', () => {
    const sections = buildWorkspaceHomeSections({
      locale: 'en-US',
      now: new Date('2026-06-10T03:00:00Z'),
      state: {
        meetings: [],
        meetingsLoading: false,
        issues: [],
        issuesLoading: false,
        recentPages: [],
        pagesLoading: false,
        plannerEvents: [
          {
            id: 'later',
            title: 'Conference',
            allDay: true,
            start: '2026-06-18',
            end: '2026-06-18',
          } as PlannerEvent,
          {
            id: 'soon',
            title: 'Sync',
            allDay: false,
            start: '2026-06-10T05:00:00Z',
            end: '2026-06-10T06:00:00Z',
          } as PlannerEvent,
        ],
        plannerLoading: false,
        notifications: [],
        notificationsLoading: false,
      },
      timeZone: 'UTC',
      t,
      workspaceSlug: 'team alpha',
    });

    const planner = sections.find((section) => section.id === 'planner');
    expect(planner?.status).toBe('ready');
    expect(planner?.rows).toMatchObject([
      {
        kind: 'planner',
        id: 'soon',
        to: '/apps/planner',
      },
      {
        kind: 'planner',
        id: 'later',
        to: '/apps/planner',
      },
    ]);
  });

  it('builds notification rows with resolved deep links', () => {
    const sections = buildWorkspaceHomeSections({
      locale: 'en-US',
      now: new Date('2026-06-10T03:00:00Z'),
      state: {
        meetings: [],
        meetingsLoading: false,
        issues: [],
        issuesLoading: false,
        recentPages: [],
        pagesLoading: false,
        plannerEvents: [],
        plannerLoading: false,
        notifications: [
          {
            id: 'n1',
            type: 'task',
            title: 'Assigned to you',
            body: 'Task X',
            reference_type: 'task',
            reference_id: 'task-9',
            action_url: null,
            is_read: false,
            created_at: '2026-06-10T02:00:00Z',
          } as WorkspaceNotification,
          {
            id: 'n2',
            type: 'mention',
            title: 'Mentioned you',
            body: '',
            reference_type: 'doc',
            reference_id: null,
            action_url: '/apps/docs/workspaces/team%20alpha/documents/d1',
            is_read: true,
            created_at: '2026-06-09T02:00:00Z',
          } as WorkspaceNotification,
        ],
        notificationsLoading: false,
      },
      timeZone: 'UTC',
      t,
      workspaceSlug: 'team alpha',
    });

    const notifications = sections.find(
      (section) => section.id === 'notifications',
    );
    expect(notifications?.status).toBe('ready');
    expect(notifications?.rows).toMatchObject([
      {
        kind: 'notification',
        id: 'n1',
        to: '/apps/pms/workspaces/team%20alpha/assigned?task=task-9',
        isRead: false,
      },
      {
        kind: 'notification',
        id: 'n2',
        to: '/apps/docs/workspaces/team%20alpha/documents/d1',
        isRead: true,
      },
    ]);
  });

  it('tracks independent loading and failure states', () => {
    const loadingState = workspaceHomeReducer(INITIAL_WORKSPACE_HOME_STATE, {
      type: 'load-started',
    });
    expect(loadingState.meetingsLoading).toBe(true);
    expect(loadingState.issuesLoading).toBe(true);
    expect(loadingState.pagesLoading).toBe(true);

    const loadedState = workspaceHomeReducer(loadingState, {
      type: 'meetings-loaded',
      items: [meeting('a', '2026-01-10T00:00:00Z')],
    });
    expect(loadedState.meetings).toHaveLength(1);
    expect(loadedState.meetingsLoading).toBe(false);

    const failedState = workspaceHomeReducer(loadedState, {
      type: 'meetings-failed',
    });
    expect(failedState.meetings).toEqual([]);
    expect(failedState.meetingsLoading).toBe(false);
  });
});
