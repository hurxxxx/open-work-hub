import { describe, expect, it } from 'vitest';
import type { RecentPageItem } from '@/src/app-modules/docs/public-api';
import type { MeetingListItem } from '@/src/app-modules/meeting/public-api';
import type { PlannerEvent } from '@/src/app-modules/planner/public-api';
import type { PmsTask } from '@/src/app-modules/pms/public-api';
import {
  INITIAL_HOME_STATE,
  buildHomeSections,
  formatHomeDueDate,
  getHomeGreeting,
  selectTodayMeetings,
  selectTopAssignedTasks,
  selectTopRecentPages,
  homePriorityTone,
  homeReducer,
} from './home-model';

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

describe('home-model', () => {
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
      selectTopAssignedTasks([1, 2, 3, 4, 5, 6].map((id) => task(String(id)))),
    ).toHaveLength(5);
    expect(
      selectTopRecentPages([1, 2, 3, 4, 5, 6].map((id) => page(String(id)))),
    ).toHaveLength(5);
  });

  it('maps task priorities to summary tones', () => {
    expect(homePriorityTone('critical')).toBe('danger');
    expect(homePriorityTone('high')).toBe('danger');
    expect(homePriorityTone('medium')).toBe('warning');
    expect(homePriorityTone('low')).toBe('muted');
    expect(homePriorityTone(undefined)).toBe('muted');
  });

  it('builds loading, empty, and ready home summary sections', () => {
    expect(
      buildHomeSections({
        locale: 'en-US',
        now: new Date('2026-01-10T12:00:00Z'),
        state: INITIAL_HOME_STATE,
        timeZone: 'UTC',
        t,
      }).map((section) => [section.id, section.status, section.actionTo]),
    ).toEqual([
      ['planner', 'loading', '/apps/planner'],
      ['meetings', 'loading', '/apps/meeting'],
      ['tasks', 'loading', '/apps/pms/assigned'],
      ['docs', 'loading', '/apps/docs'],
    ]);

    expect(
      buildHomeSections({
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
        },
        timeZone: 'UTC',
        t,
      }).map((section) => [section.id, section.status]),
    ).toEqual([
      ['planner', 'empty'],
      ['meetings', 'empty'],
      ['tasks', 'empty'],
      ['docs', 'empty'],
    ]);
  });

  it('projects loaded meetings, tasks, and docs into stable rows', () => {
    const sections = buildHomeSections({
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
      },
      timeZone: 'UTC',
      t,
    });

    expect(sections[1]?.rows).toMatchObject([
      {
        kind: 'meeting',
        id: 'today',
        title: 'Meeting today',
        to: '/apps/meeting/meetings/today',
      },
    ]);
    expect(sections[2]?.rows).toEqual([
      {
        kind: 'task',
        id: 'due',
        title: 'Task due',
        to: '/apps/pms/assigned?task=due',
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
        to: '/apps/docs/documents/doc-1',
      },
    ]);
  });

  it('orders upcoming planner events by start and links to the planner app', () => {
    const sections = buildHomeSections({
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
      },
      timeZone: 'UTC',
      t,
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

  it('tracks independent loading and failure states', () => {
    const loadingState = homeReducer(INITIAL_HOME_STATE, {
      type: 'load-started',
    });
    expect(loadingState.meetingsLoading).toBe(true);
    expect(loadingState.issuesLoading).toBe(true);
    expect(loadingState.pagesLoading).toBe(true);

    const loadedState = homeReducer(loadingState, {
      type: 'meetings-loaded',
      items: [meeting('a', '2026-01-10T00:00:00Z')],
    });
    expect(loadedState.meetings).toHaveLength(1);
    expect(loadedState.meetingsLoading).toBe(false);

    const failedState = homeReducer(loadedState, {
      type: 'meetings-failed',
    });
    expect(failedState.meetings).toEqual([]);
    expect(failedState.meetingsLoading).toBe(false);
  });
});
