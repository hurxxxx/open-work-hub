import type { RecentPageItem } from '@/src/app-modules/docs/public-api';
import type { MeetingListItem } from '@/src/app-modules/meeting/public-api';
import type { PlannerEvent } from '@/src/app-modules/planner/public-api';
import type { PmsTask } from '@/src/app-modules/pms/public-api';
import {
  diffDateOnlyDays,
  formatDateOnly,
  formatDateTime,
  getZonedDateParts,
  isSameDateInTimeZone,
  parseApiDateTime,
  zonedDateKey,
} from '@/src/platform/time/time-utils';
import {
  buildAppEntryHref,
  buildAppHref,
} from '@open-work-hub/contracts/app-routes';

type Translate = (key: string, options?: Record<string, unknown>) => string;

export type HomeSectionStatus = 'loading' | 'empty' | 'ready';

export type HomePriorityTone = 'danger' | 'warning' | 'muted';

export type HomeRow =
  | {
      kind: 'meeting';
      id: string;
      title: string;
      to: string;
      trailing: string;
    }
  | {
      kind: 'task';
      id: string;
      title: string;
      to: string;
      trailing: string;
      priorityTone: HomePriorityTone;
    }
  | {
      kind: 'doc';
      id: string;
      title: string;
      subtitle: string;
      to: string;
    }
  | {
      kind: 'planner';
      id: string;
      title: string;
      to: string;
      trailing: string;
    };

export type HomeSection = {
  id: 'meetings' | 'tasks' | 'docs' | 'planner';
  titleKey: string;
  actionLabelKey: string;
  actionTo: string;
  emptyKey: string;
  emptyCtaLabelKey: string;
  emptyCtaTo: string;
  status: HomeSectionStatus;
  rows: HomeRow[];
};

export type HomeBriefing = {
  status: 'loading' | 'empty' | 'ready';
  meetings: number;
  tasks: number;
  docs: number;
  events: number;
};

export interface HomeState {
  meetings: MeetingListItem[];
  meetingsLoading: boolean;
  issues: PmsTask[];
  issuesLoading: boolean;
  recentPages: RecentPageItem[];
  pagesLoading: boolean;
  plannerEvents: PlannerEvent[];
  plannerLoading: boolean;
}

export type HomeAction =
  | { type: 'load-started' }
  | { type: 'meetings-loaded'; items: MeetingListItem[] }
  | { type: 'meetings-failed' }
  | { type: 'issues-loaded'; items: PmsTask[] }
  | { type: 'issues-failed' }
  | { type: 'pages-loaded'; items: RecentPageItem[] }
  | { type: 'pages-failed' }
  | { type: 'planner-loaded'; items: PlannerEvent[] }
  | { type: 'planner-failed' };

export const INITIAL_HOME_STATE: HomeState = {
  meetings: [],
  meetingsLoading: true,
  issues: [],
  issuesLoading: true,
  recentPages: [],
  pagesLoading: true,
  plannerEvents: [],
  plannerLoading: true,
};

export function getHomeGreeting(
  timeZone: string,
  t: Translate,
  now: Date = new Date(),
): string {
  const hour = getZonedDateParts(now, timeZone)?.hour ?? now.getHours();
  if (hour < 12) return t('home.greetingMorning');
  if (hour < 18) return t('home.greetingAfternoon');
  return t('home.greetingEvening');
}

export function formatHomeWeekday(
  date: Date,
  timeZone: string,
  locale: string,
): string {
  return formatDateTime(date, {
    locale,
    month: 'long',
    day: 'numeric',
    weekday: 'long',
    timeZone,
  });
}

export function formatHomeTime(
  iso: string,
  timeZone: string,
  locale: string,
): string {
  return formatDateTime(iso, {
    hour: 'numeric',
    locale,
    minute: '2-digit',
    timeZone,
  });
}

export function formatHomeDueDate(
  due: string | null,
  timeZone: string,
  locale: string,
  t: Translate,
  now: Date = new Date(),
): string {
  if (!due) return '';
  const diffDays = diffDateOnlyDays(due, zonedDateKey(now, timeZone));
  if (diffDays === null) return '';
  if (diffDays === 0) return t('home.dueToday');
  if (diffDays === 1) return t('home.dueTomorrow');
  if (diffDays === -1) return t('home.dueYesterday');
  if (diffDays < 0) return t('home.dueOverdue', { count: -diffDays });
  if (diffDays < 7) return t('home.dueInDays', { count: diffDays });
  return formatDateOnly(due, {
    locale,
    month: 'short',
    day: 'numeric',
  });
}

export function selectTodayMeetings(
  meetings: MeetingListItem[],
  timeZone: string,
  now: Date = new Date(),
  limit = 5,
): MeetingListItem[] {
  return meetings
    .filter((meeting) => isSameDateInTimeZone(meeting.start_at, now, timeZone))
    .slice(0, limit);
}

export function selectTopAssignedTasks(
  issues: PmsTask[],
  limit = 5,
): PmsTask[] {
  return issues.slice(0, limit);
}

export function selectTopRecentPages(
  pages: RecentPageItem[],
  limit = 5,
): RecentPageItem[] {
  return pages.slice(0, limit);
}

export function selectUpcomingPlannerEvents(
  events: PlannerEvent[],
  limit = 6,
): PlannerEvent[] {
  return [...events]
    .sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0))
    .slice(0, limit);
}

export function formatHomeEventWhen(
  start: string,
  allDay: boolean,
  timeZone: string,
  locale: string,
  t: Translate,
  now: Date = new Date(),
): string {
  const startDate = parseApiDateTime(start);
  const dateKey =
    allDay || !startDate
      ? start.slice(0, 10)
      : zonedDateKey(startDate, timeZone);
  const dayLabel = formatHomeDueDate(dateKey, timeZone, locale, t, now);
  if (allDay || !startDate) return dayLabel;
  const time = formatHomeTime(start, timeZone, locale);
  return dayLabel ? `${dayLabel} ${time}` : time;
}

export function workspaceHomePriorityTone(
  priority: string | null | undefined,
): HomePriorityTone {
  if (priority === 'critical' || priority === 'high') return 'danger';
  if (priority === 'medium') return 'warning';
  return 'muted';
}

function sectionStatus(
  loading: boolean,
  rows: readonly HomeRow[],
): HomeSectionStatus {
  if (loading) return 'loading';
  return rows.length > 0 ? 'ready' : 'empty';
}

export function buildHomeBriefing({
  now = new Date(),
  state,
  timeZone,
}: {
  now?: Date;
  state: HomeState;
  timeZone: string;
}): HomeBriefing {
  if (
    state.meetingsLoading ||
    state.issuesLoading ||
    state.pagesLoading ||
    state.plannerLoading
  ) {
    return { status: 'loading', meetings: 0, tasks: 0, docs: 0, events: 0 };
  }
  const meetings = selectTodayMeetings(state.meetings, timeZone, now).length;
  const tasks = state.issues.length;
  const docs = state.recentPages.length;
  const events = state.plannerEvents.length;
  const status = meetings + tasks + docs + events === 0 ? 'empty' : 'ready';
  return { status, meetings, tasks, docs, events };
}

export function buildHomeSections({
  locale,
  now = new Date(),
  state,
  timeZone,
  t,
}: {
  locale: string;
  now?: Date;
  state: HomeState;
  timeZone: string;
  t: Translate;
}): HomeSection[] {
  const meetingRoot = buildAppHref({ routeId: 'meeting.root' });
  const assignedLink = buildAppHref({ routeId: 'pms.assigned' });
  const docsRoot = buildAppHref({ routeId: 'docs.root' });
  const plannerRoot = buildAppEntryHref('planner');
  const meetingCreate = buildAppHref({
    routeId: 'meeting.root',
    queryParams: { create: '1' },
  });
  const taskCreate = buildAppHref({
    routeId: 'pms.root',
    queryParams: { create: '1' },
  });
  const docCreate = buildAppHref({
    routeId: 'docs.root',
    queryParams: { create: '1' },
  });

  const plannerRows = selectUpcomingPlannerEvents(
    state.plannerEvents,
  ).map<HomeRow>((event) => ({
    kind: 'planner',
    id: event.id,
    title: event.title,
    to: plannerRoot,
    trailing: formatHomeEventWhen(
      event.start,
      event.allDay,
      timeZone,
      locale,
      t,
      now,
    ),
  }));

  const meetingRows = selectTodayMeetings(
    state.meetings,
    timeZone,
    now,
  ).map<HomeRow>((meeting) => ({
    kind: 'meeting',
    id: meeting.id,
    title: meeting.title,
    to: buildAppHref({
      routeId: 'meeting.detail',
      pathParams: { meetingId: meeting.id },
    }),
    trailing: formatHomeTime(meeting.start_at, timeZone, locale),
  }));

  const taskRows = selectTopAssignedTasks(state.issues).map<HomeRow>(
    (issue) => ({
      kind: 'task',
      id: issue.id,
      title: issue.title,
      to: buildAppHref({
        routeId: 'pms.assigned',
        queryParams: { task: issue.id },
      }),
      trailing: issue.due_date
        ? formatHomeDueDate(issue.due_date, timeZone, locale, t, now)
        : '',
      priorityTone: workspaceHomePriorityTone(issue.priority),
    }),
  );

  const docRows = selectTopRecentPages(state.recentPages).map<HomeRow>(
    (page) => ({
      kind: 'doc',
      id: page.page_id,
      title: page.page_title || t('home.untitled'),
      subtitle: page.doc_title,
      to: buildAppHref({
        routeId: 'docs.document',
        pathParams: { docId: page.doc_id },
      }),
    }),
  );

  return [
    {
      id: 'planner',
      titleKey: 'home.upcomingSchedule',
      actionLabelKey: 'home.seeAll',
      actionTo: plannerRoot,
      emptyKey: 'home.scheduleEmpty',
      emptyCtaLabelKey: 'home.scheduleEmptyCta',
      emptyCtaTo: plannerRoot,
      status: sectionStatus(state.plannerLoading, plannerRows),
      rows: plannerRows,
    },
    {
      id: 'meetings',
      titleKey: 'home.todayMeetings',
      actionLabelKey: 'home.seeAll',
      actionTo: meetingRoot,
      emptyKey: 'home.meetingsEmpty',
      emptyCtaLabelKey: 'home.meetingsEmptyCta',
      emptyCtaTo: meetingCreate,
      status: sectionStatus(state.meetingsLoading, meetingRows),
      rows: meetingRows,
    },
    {
      id: 'tasks',
      titleKey: 'home.myTasks',
      actionLabelKey: 'home.seeAll',
      actionTo: assignedLink,
      emptyKey: 'home.tasksEmpty',
      emptyCtaLabelKey: 'home.tasksEmptyCta',
      emptyCtaTo: taskCreate,
      status: sectionStatus(state.issuesLoading, taskRows),
      rows: taskRows,
    },
    {
      id: 'docs',
      titleKey: 'home.recentDocs',
      actionLabelKey: 'home.seeAll',
      actionTo: docsRoot,
      emptyKey: 'home.docsEmpty',
      emptyCtaLabelKey: 'home.docsEmptyCta',
      emptyCtaTo: docCreate,
      status: sectionStatus(state.pagesLoading, docRows),
      rows: docRows,
    },
  ];
}

export function workspaceHomeReducer(
  state: HomeState,
  action: HomeAction,
): HomeState {
  switch (action.type) {
    case 'load-started':
      return {
        ...state,
        meetingsLoading: true,
        issuesLoading: true,
        pagesLoading: true,
        plannerLoading: true,
      };
    case 'meetings-loaded':
      return { ...state, meetings: action.items, meetingsLoading: false };
    case 'meetings-failed':
      return { ...state, meetings: [], meetingsLoading: false };
    case 'issues-loaded':
      return { ...state, issues: action.items, issuesLoading: false };
    case 'issues-failed':
      return { ...state, issues: [], issuesLoading: false };
    case 'pages-loaded':
      return { ...state, recentPages: action.items, pagesLoading: false };
    case 'pages-failed':
      return { ...state, recentPages: [], pagesLoading: false };
    case 'planner-loaded':
      return { ...state, plannerEvents: action.items, plannerLoading: false };
    case 'planner-failed':
      return { ...state, plannerEvents: [], plannerLoading: false };
  }
}
