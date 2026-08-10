import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  CalendarDays,
  CalendarPlus,
  ExternalLink,
  Loader2,
  MapPin,
} from 'lucide-react';
import { Button, InlineNotice } from '@open-alm/ui';

import { cn } from '@/src/lib/utils';
import type {
  CalendarEvent,
  CalendarSourceFilter,
  CalendarSourceType,
} from '@/src/platform/calendar/calendar-types';
import { listCalendarEvents } from '@/src/platform/calendar/calendar-api';
import { useCalendarEvents } from '@/src/platform/calendar/use-calendar-events';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateOnly,
  formatDateTime,
  normalizeTimeZone,
  parseApiDateTime,
} from '@/src/platform/time/time-utils';
import { dispatchFloatingPmsOpen } from '@/src/platform/personal-widgets/floating-panel-events';

import { MeetingPreviewModal } from './calendar/MeetingPreviewModal';
import { PlannerEventModal } from './PlannerEventModal';
import { resolvePlannerCalendarEventClick } from './planner-calendar-controller';
import {
  addDateKeyDays,
  buildCreateRangeForDateKey,
  buildTodayPlannerDayGroups,
  buildTodayPlannerRange,
  countRemainingTodayPlannerEntries,
  type TodayPlannerDayId,
  type TodayPlannerEntry,
} from './floating-today-planner-model';

const CLOCK_TICK_MS = 60_000;

const DAY_LABEL_KEYS: Record<TodayPlannerDayId, string> = {
  tomorrow: 'planner.floating.days.tomorrow',
  today: 'planner.floating.days.today',
  yesterday: 'planner.floating.days.yesterday',
};

const SOURCE_LABEL_KEYS: Record<CalendarSourceType, string> = {
  meeting: 'planner.floating.sources.meeting',
  planner_event: 'planner.floating.sources.plannerEvent',
  pms_block: 'planner.floating.sources.pmsBlock',
  pms_due: 'planner.floating.sources.pmsDue',
};

const SOURCE_CHIP_CLASS_NAMES: Record<CalendarSourceType, string> = {
  meeting: 'bg-app-info/10 text-app-info-text dark:text-app-info-text',
  planner_event: 'bg-teal-500/10 text-teal-700 dark:text-teal-300',
  pms_block:
    'bg-app-success/10 text-app-success-text dark:text-app-success-text',
  pms_due: 'bg-app-warning/15 text-app-warning-text dark:text-app-warning-text',
};

const TODAY_PLANNER_SOURCES = [
  'meeting',
  'pms_due',
  'pms_block',
  'planner_event',
] as const satisfies CalendarSourceFilter;

type TranslationFn = (key: string, options?: Record<string, unknown>) => string;

interface PlannerEventTimeMetadata {
  plannerAllDay?: boolean | null;
  plannerStartHasTime?: boolean | null;
  plannerEndHasTime?: boolean | null;
}

export function FloatingTodayPlannerWidget({
  onChanged,
  reloadSeq = 0,
}: {
  onChanged?: () => void;
  reloadSeq?: number;
}) {
  const { i18n, t } = useTranslation('apps');
  const { user } = useAuth();
  const navigate = useNavigate();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [activeDayId, setActiveDayId] = useState<TodayPlannerDayId>('today');
  const [plannerEventModalOpen, setPlannerEventModalOpen] = useState(false);
  const [plannerEventId, setPlannerEventId] = useState<string | null>(null);
  const [plannerEventRange, setPlannerEventRange] = useState<ReturnType<
    typeof buildCreateRangeForDateKey
  > | null>(null);
  const [previewMeetingId, setPreviewMeetingId] = useState<string | null>(null);
  const [previewMeetingWorkspaceSlug, setPreviewMeetingWorkspaceSlug] =
    useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const previousReloadSeq = useRef(reloadSeq);
  const now = useMemo(() => new Date(clockTick), [clockTick]);
  const range = useMemo(
    () => buildTodayPlannerRange(now, timeZone),
    [now, timeZone],
  );
  const { events, loading, error, refresh } = useCalendarEvents({
    from: range.from,
    sources: TODAY_PLANNER_SOURCES,
    to: range.to,
    useMockData: false,
  });
  const groups = useMemo(
    () => buildTodayPlannerDayGroups(events, range.days, timeZone, now),
    [events, now, range.days, timeZone],
  );
  const activeGroup =
    groups.find((group) => group.id === activeDayId) ?? groups[1] ?? groups[0];
  const todayGroup = groups.find((group) => group.id === 'today');
  const todayRemainingCount =
    todayGroup?.entries.filter((entry) => !entry.isPast).length ?? 0;

  useEffect(() => {
    const id = window.setInterval(
      () => setClockTick(Date.now()),
      CLOCK_TICK_MS,
    );
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const handleFocus = () => {
      setClockTick(Date.now());
      refresh();
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [refresh]);

  useEffect(() => {
    if (!actionError) {
      return undefined;
    }
    const id = window.setTimeout(() => setActionError(null), 4000);
    return () => window.clearTimeout(id);
  }, [actionError]);

  useEffect(() => {
    if (previousReloadSeq.current === reloadSeq) {
      return;
    }
    previousReloadSeq.current = reloadSeq;
    setClockTick(Date.now());
    refresh();
  }, [refresh, reloadSeq]);

  const handlePlannerChanged = useCallback(() => {
    setPlannerEventModalOpen(false);
    setPlannerEventId(null);
    setPlannerEventRange(null);
    refresh();
    onChanged?.();
  }, [onChanged, refresh]);

  const openCreatePlannerEvent = useCallback(() => {
    const dateKey = activeGroup?.dateKey ?? range.todayKey;
    setPlannerEventId(null);
    setPlannerEventRange(buildCreateRangeForDateKey(dateKey));
    setPlannerEventModalOpen(true);
  }, [activeGroup?.dateKey, range.todayKey]);

  const handleEventClick = useCallback(
    (event: CalendarEvent) => {
      const action = resolvePlannerCalendarEventClick(event);
      if (action.type === 'openPlannerEvent') {
        setPlannerEventId(action.eventId);
        setPlannerEventRange(null);
        setPlannerEventModalOpen(true);
        return;
      }
      if (action.type === 'previewMeeting') {
        setPreviewMeetingId(action.meetingId);
        setPreviewMeetingWorkspaceSlug(action.workspaceSlug);
        return;
      }
      if (action.type === 'openTask') {
        dispatchFloatingPmsOpen({
          mode: 'openTask',
          taskId: action.taskId,
          taskListId: action.taskListId,
          workspaceSlug: action.workspaceSlug,
        });
        return;
      }
      if (action.type === 'missingTaskList') {
        setActionError(t('planner.taskLocationMissing'));
      }
    },
    [t],
  );

  return (
    <div className="flex h-full min-w-0 flex-col bg-app-bg text-app-ink">
      <section className="flex shrink-0 items-center justify-between gap-3 border-b border-app-border px-4 py-3">
        <div className="min-w-0">
          <h4 className="app-text-title-sm text-app-ink">
            {t('planner.floating.title')}
          </h4>
          <p className="app-text-caption text-app-ink/45">
            {t('planner.floating.todayRemaining', {
              count: todayRemainingCount,
            })}
          </p>
        </div>
        <Button
          className="shrink-0 gap-1.5"
          onClick={openCreatePlannerEvent}
          variant="primary"
        >
          <CalendarPlus aria-hidden="true" size={15} />
          <span>{t('planner.floating.addPlan')}</span>
        </Button>
      </section>

      <div className="grid shrink-0 grid-cols-3 gap-1 border-b border-app-border bg-app-surface-sidebar/40 px-3 py-2">
        {groups.map((group) => (
          <button
            aria-pressed={activeDayId === group.id}
            className={cn(
              'min-w-0 rounded-md px-2 py-2 text-center transition-colors',
              activeDayId === group.id
                ? 'bg-app-bg text-app-ink shadow-sm'
                : 'text-app-ink/55 hover:bg-app-surface-hover hover:text-app-ink',
            )}
            key={group.id}
            onClick={() => setActiveDayId(group.id)}
            type="button"
          >
            <span className="app-text-control-sm block truncate">
              {t(DAY_LABEL_KEYS[group.id])}
            </span>
            <span className="app-text-micro mt-0.5 block truncate">
              {formatDateOnly(group.dateKey, {
                day: 'numeric',
                locale: i18n.language,
                month: 'short',
              })}
            </span>
            <span className="app-text-micro mt-1 inline-flex min-w-5 justify-center rounded-full bg-app-surface px-1.5 py-0.5 text-app-ink/55">
              {group.entries.length}
            </span>
          </button>
        ))}
      </div>

      {error || actionError ? (
        <div className="shrink-0 px-4 py-3">
          <InlineNotice tone="danger">
            {actionError ?? error ?? t('planner.loadFailed')}
          </InlineNotice>
        </div>
      ) : null}

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
        {loading && events.length === 0 ? (
          <div className="flex h-full items-center justify-center text-app-ink/40">
            <Loader2 aria-hidden="true" className="animate-spin" size={20} />
          </div>
        ) : activeGroup && activeGroup.entries.length > 0 ? (
          <ul className="divide-y divide-app-border">
            {activeGroup.entries.map((entry) => (
              <TodayPlannerEntryRow
                entry={entry}
                key={entry.id}
                locale={i18n.language}
                onClick={() => handleEventClick(entry.event)}
                timeZone={timeZone}
              />
            ))}
          </ul>
        ) : (
          <div className="flex h-full items-center justify-center px-6 text-center">
            <div className="grid justify-items-center gap-2">
              <CalendarDays
                aria-hidden="true"
                className="text-app-ink/25"
                size={24}
              />
              <p className="app-text-body-sm text-app-ink/45">
                {t('planner.floating.emptyDay')}
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="flex shrink-0 justify-end border-t border-app-border px-4 py-3">
        <Button
          className="gap-1.5"
          onClick={() => navigate('/planner')}
          variant="secondary"
        >
          <ExternalLink aria-hidden="true" size={14} />
          <span>{t('planner.floating.openFullPlanner')}</span>
        </Button>
      </div>

      <MeetingPreviewModal
        contentClassName="z-[120]"
        meetingId={previewMeetingId}
        onChanged={() => {
          refresh();
          onChanged?.();
        }}
        onClose={() => {
          setPreviewMeetingId(null);
          setPreviewMeetingWorkspaceSlug(null);
        }}
        overlayClassName="z-[119]"
        workspaceSlug={previewMeetingWorkspaceSlug ?? undefined}
      />
      <PlannerEventModal
        contentClassName="z-[120]"
        eventId={plannerEventId}
        initialRange={plannerEventRange}
        isOpen={plannerEventModalOpen}
        onClose={() => {
          setPlannerEventModalOpen(false);
          setPlannerEventId(null);
          setPlannerEventRange(null);
        }}
        onDeleted={handlePlannerChanged}
        onSaved={handlePlannerChanged}
        overlayClassName="z-[119]"
      />
    </div>
  );
}

function TodayPlannerEntryRow({
  entry,
  locale,
  onClick,
  timeZone,
}: {
  entry: TodayPlannerEntry;
  locale: string;
  onClick: () => void;
  timeZone: string;
}) {
  const { t } = useTranslation('apps');
  const event = entry.event;
  const location = event.metadata.location;

  return (
    <li>
      <button
        aria-label={t('planner.floating.openItem', { title: event.title })}
        className={cn(
          'w-full px-4 py-3 text-left transition-colors hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-inset focus:ring-app-accent/30',
          entry.isPast && 'opacity-55',
        )}
        onClick={onClick}
        type="button"
      >
        <div className="flex min-w-0 items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-1 size-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: event.color }}
          />
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <p className="app-text-body-sm line-clamp-2 text-app-ink">
                {event.title}
              </p>
              <span className="app-text-caption shrink-0 whitespace-nowrap text-app-ink/45">
                {formatEntryTime(event, locale, timeZone, t)}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span
                className={cn(
                  'app-text-micro rounded-full px-2 py-0.5',
                  SOURCE_CHIP_CLASS_NAMES[event.sourceType],
                )}
              >
                {t(SOURCE_LABEL_KEYS[event.sourceType])}
              </span>
              {event.workspace ? (
                <span
                  className="app-text-micro max-w-36 truncate rounded-full bg-app-surface-sidebar px-2 py-0.5 text-app-ink/50"
                  title={event.workspace.name}
                >
                  {event.workspace.name}
                </span>
              ) : null}
              {location ? (
                <span className="app-text-micro inline-flex min-w-0 items-center gap-1 text-app-ink/45">
                  <MapPin aria-hidden="true" size={12} />
                  <span className="truncate">{location}</span>
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </button>
    </li>
  );
}

function formatEntryTime(
  event: CalendarEvent,
  locale: string,
  timeZone: string,
  t: TranslationFn,
): string {
  if (event.sourceType === 'planner_event') {
    const metadata = event.metadata as CalendarEvent['metadata'] &
      PlannerEventTimeMetadata;
    const plannerAllDay = metadata.plannerAllDay ?? event.allDay;
    const startHasTime =
      metadata.plannerStartHasTime ??
      (!event.allDay && event.start.includes('T'));
    const endHasTime =
      metadata.plannerEndHasTime ?? (!event.allDay && event.end.includes('T'));

    if (plannerAllDay) {
      return t('planner.floating.allDay');
    }
    if (!startHasTime && !endHasTime) {
      return t('planner.floating.timeUnspecified');
    }

    const start = parseApiDateTime(event.start);
    const end = parseApiDateTime(event.end);
    const startLabel = start
      ? formatDateTime(start, {
          hour: 'numeric',
          locale,
          minute: '2-digit',
          timeZone,
        })
      : '';
    const endLabel = end
      ? formatDateTime(end, {
          hour: 'numeric',
          locale,
          minute: '2-digit',
          timeZone,
        })
      : '';

    if (startHasTime && endHasTime && startLabel && endLabel) {
      return `${startLabel} - ${endLabel}`;
    }
    if (startHasTime && startLabel) {
      return startLabel;
    }
    if (endHasTime && endLabel) {
      return t('planner.floating.endsAt', { time: endLabel });
    }
    return t('planner.floating.timeUnspecified');
  }

  if (event.allDay) {
    return t('planner.floating.allDay');
  }
  const start = parseApiDateTime(event.start);
  const end = parseApiDateTime(event.end);
  if (!start) {
    return '';
  }
  const startLabel = formatDateTime(start, {
    hour: 'numeric',
    locale,
    minute: '2-digit',
    timeZone,
  });
  if (!end) {
    return startLabel;
  }
  const endLabel = formatDateTime(end, {
    hour: 'numeric',
    locale,
    minute: '2-digit',
    timeZone,
  });
  return `${startLabel} - ${endLabel}`;
}

export function useFloatingTodayPlannerCount(
  token: string | null,
  timeZone: string,
  reloadSeq = 0,
): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setCount(0);
      return undefined;
    }

    const now = new Date();
    const range = buildTodayPlannerRange(now, timeZone);
    listCalendarEvents(token, {
      from: range.todayKey,
      sources: TODAY_PLANNER_SOURCES,
      to: addDateKeyDays(range.todayKey, 1),
    })
      .then((response) => {
        if (cancelled) {
          return;
        }
        setCount(
          countRemainingTodayPlannerEntries(
            response.items,
            range.todayKey,
            timeZone,
            now,
          ),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setCount(0);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reloadSeq, timeZone, token]);

  return count;
}
