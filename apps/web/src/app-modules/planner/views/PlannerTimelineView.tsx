import {
  useCallback,
  useMemo,
  useState,
  useSyncExternalStore,
  type CSSProperties,
} from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import type {
  CalendarEvent,
  CalendarSourceType,
} from '@/src/platform/calendar/calendar-types';
import {
  addDays,
  buildDays,
  buildItemGroups,
  buildMonthSpans,
  buildTimelineItems,
  dateOnlyToLocalDate,
  diffDays,
  diffTimestampDays,
  getTimelineDayWidth,
  startOfLocalDay,
  type TimelineItem,
} from './planner-timeline-model';

const LEFT_COLUMN_WIDTH = 320;

const SOURCE_LABEL_KEYS: Record<CalendarSourceType, string> = {
  meeting: 'planner.timeline.sources.meeting',
  pms_block: 'planner.timeline.sources.pmsBlock',
  pms_due: 'planner.timeline.sources.pmsDue',
  planner_event: 'planner.timeline.sources.plannerEvent',
};

interface PlannerTimelineViewProps {
  events: CalendarEvent[];
  rangeStart: string;
  rangeEnd: string;
  locale: string;
  timeZone: string;
  onEventClick: (event: CalendarEvent) => void;
}

interface TimelineFormatters {
  month: Intl.DateTimeFormat;
  day: Intl.DateTimeFormat;
  weekday: Intl.DateTimeFormat;
  itemDate: Intl.DateTimeFormat;
  itemTime: Intl.DateTimeFormat;
}

function formatDayLabel(date: Date, formatter: Intl.DateTimeFormat): string {
  return formatter.format(date);
}

function formatWeekday(date: Date, formatter: Intl.DateTimeFormat): string {
  return formatter.format(date);
}

function formatItemTime(
  item: TimelineItem,
  formatters: TimelineFormatters,
): string {
  if (item.event.allDay) {
    const endVisible = addDays(item.endExclusive, -1);
    if (diffDays(endVisible, item.start) <= 0) {
      return formatters.itemDate.format(item.start);
    }
    return `${formatters.itemDate.format(item.start)} - ${formatters.itemDate.format(endVisible)}`;
  }

  return `${formatters.itemDate.format(item.start)} ${formatters.itemTime.format(item.start)}`;
}

function sourceCountLabel(
  count: number,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  return t('planner.timeline.itemCount', { count });
}

function subscribeTodayTimestamp(): () => void {
  return () => undefined;
}

function getTodayTimestampSnapshot(): number | null {
  return startOfLocalDay(new Date()).getTime();
}

function getServerTodayTimestampSnapshot(): null {
  return null;
}

function getServerElementWidthSnapshot(): undefined {
  return undefined;
}

function useObservedElementWidth<TElement extends HTMLElement>(): [
  (node: TElement | null) => void,
  number | undefined,
] {
  const [element, setElement] = useState<TElement | null>(null);

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (!element || typeof ResizeObserver === 'undefined') {
        return () => undefined;
      }

      const resizeObserver = new ResizeObserver(onStoreChange);
      resizeObserver.observe(element);
      return () => resizeObserver.disconnect();
    },
    [element],
  );

  const getSnapshot = useCallback(() => element?.clientWidth, [element]);

  return [
    setElement,
    useSyncExternalStore(subscribe, getSnapshot, getServerElementWidthSnapshot),
  ];
}

function useTimelineFormatters(
  locale: string,
  timeZone: string,
): TimelineFormatters {
  return useMemo(
    () => ({
      month: new Intl.DateTimeFormat(locale, {
        month: 'long',
        year: 'numeric',
      }),
      day: new Intl.DateTimeFormat(locale, { day: 'numeric' }),
      weekday: new Intl.DateTimeFormat(locale, { weekday: 'short' }),
      itemDate: new Intl.DateTimeFormat(locale, {
        day: 'numeric',
        month: 'short',
        timeZone,
      }),
      itemTime: new Intl.DateTimeFormat(locale, {
        hour: 'numeric',
        minute: '2-digit',
        timeZone,
      }),
    }),
    [locale, timeZone],
  );
}

export function PlannerTimelineView(props: PlannerTimelineViewProps) {
  return usePlannerTimelineViewElement(props);
}

function usePlannerTimelineViewElement({
  events,
  rangeStart,
  rangeEnd,
  locale,
  timeZone,
  onEventClick,
}: PlannerTimelineViewProps) {
  const { t } = useTranslation('apps');
  const [containerRef, viewportWidth] =
    useObservedElementWidth<HTMLDivElement>();
  const todayTimestamp = useSyncExternalStore(
    subscribeTodayTimestamp,
    getTodayTimestampSnapshot,
    getServerTodayTimestampSnapshot,
  );
  const formatters = useTimelineFormatters(locale, timeZone);
  const rangeStartDate = useMemo(
    () => dateOnlyToLocalDate(rangeStart) ?? new Date(todayTimestamp ?? 0),
    [rangeStart, todayTimestamp],
  );
  const rangeEndDate = useMemo(
    () => dateOnlyToLocalDate(rangeEnd) ?? addDays(rangeStartDate, 1),
    [rangeEnd, rangeStartDate],
  );
  const totalDays = Math.max(1, diffDays(rangeEndDate, rangeStartDate));
  const dayWidth = getTimelineDayWidth(
    totalDays,
    viewportWidth ?? 0,
    LEFT_COLUMN_WIDTH,
  );
  const timelineWidth = totalDays * dayWidth;

  const days = useMemo(
    () => buildDays(rangeStartDate, totalDays),
    [rangeStartDate, totalDays],
  );
  const monthSpans = useMemo(
    () => buildMonthSpans(days, formatters.month),
    [days, formatters.month],
  );
  const items = useMemo(
    () =>
      buildTimelineItems(
        events,
        rangeStartDate,
        rangeEndDate,
        timeZone,
        dayWidth,
      ),
    [dayWidth, events, rangeEndDate, rangeStartDate, timeZone],
  );
  const { groupedItems, sourceCounts } = useMemo(
    () => buildItemGroups(items),
    [items],
  );
  const todayOffset =
    todayTimestamp === null
      ? null
      : diffTimestampDays(todayTimestamp, rangeStartDate);
  const todayLeft =
    todayOffset !== null && todayOffset >= 0 && todayOffset < totalDays
      ? todayOffset * dayWidth + dayWidth / 2
      : null;

  const gridBackground = days.map((day, index) => {
    const isWeekend = day.getDay() === 0 || day.getDay() === 6;
    return (
      <div
        key={day.toISOString()}
        className={cn(
          'h-full shrink-0 border-r border-app-border/70',
          isWeekend && 'bg-app-surface-sidebar/35',
          index === 0 && 'border-l',
        )}
        style={{ width: dayWidth }}
      />
    );
  });

  return (
    <div ref={containerRef} className="flex h-full min-h-0 flex-col bg-app-bg">
      <div className="flex min-h-12 flex-wrap items-center justify-between gap-3 border-b border-app-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <div className="app-text-overline text-app-ink/45">
            {t('planner.timeline.overview')}
          </div>
          <div className="app-text-caption text-app-ink/55">
            {t('planner.timeline.totalCount', { count: items.length })}
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {sourceCounts.map(({ source, count, color }) => (
            <div
              key={source}
              className="app-text-caption inline-flex items-center gap-1.5 rounded border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink/65"
            >
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span>{t(SOURCE_LABEL_KEYS[source])}</span>
              <span className="text-app-ink/40">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="text-center">
            <p className="app-text-title-sm text-app-ink">
              {t('planner.timeline.emptyTitle')}
            </p>
            <p className="app-text-body-sm mt-2 text-app-ink/50">
              {t('planner.timeline.emptyDescription')}
            </p>
          </div>
        </div>
      ) : (
        <div className="custom-scrollbar flex-1 overflow-auto">
          <div className="min-w-fit">
            <div className="sticky top-0 z-20 flex bg-app-surface">
              <div
                className="sticky left-0 z-30 shrink-0 border-r border-app-border bg-app-surface px-4 py-3"
                style={{ width: LEFT_COLUMN_WIDTH }}
              >
                <div className="app-text-overline text-app-ink/45">
                  {t('planner.timeline.itemColumn')}
                </div>
              </div>
              <div style={{ width: timelineWidth }}>
                <div className="flex h-8 border-b border-app-border">
                  {monthSpans.map((span) => (
                    <div
                      key={span.key}
                      className="app-text-overline flex items-center border-r border-app-border px-2 text-app-ink/45"
                      style={{ width: span.days * dayWidth }}
                    >
                      {span.label}
                    </div>
                  ))}
                </div>
                <div className="flex h-10 border-b border-app-border">
                  {days.map((day) => {
                    const isToday =
                      todayTimestamp !== null &&
                      day.getTime() === todayTimestamp;
                    const isSunday = day.getDay() === 0;
                    return (
                      <div
                        key={day.toISOString()}
                        className={cn(
                          'flex shrink-0 flex-col items-center justify-center border-r border-app-border/70',
                          (day.getDay() === 0 || day.getDay() === 6) &&
                            'bg-app-surface-sidebar/35',
                          isToday && 'bg-app-accent/10',
                        )}
                        style={{ width: dayWidth }}
                      >
                        <span
                          className={cn(
                            'app-text-micro',
                            isSunday ? 'text-app-danger' : 'text-app-ink/45',
                          )}
                        >
                          {formatWeekday(day, formatters.weekday)}
                        </span>
                        <span
                          className={cn(
                            'app-text-control-sm tabular-nums',
                            isToday ? 'text-app-accent' : 'text-app-ink',
                          )}
                        >
                          {formatDayLabel(day, formatters.day)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {groupedItems.map((group) => (
              <div key={group.source}>
                <div className="flex border-b border-app-border bg-app-surface-sidebar/30">
                  <div
                    className="sticky left-0 z-10 flex shrink-0 items-center justify-between border-r border-app-border bg-app-surface-sidebar px-4 py-2"
                    style={{ width: LEFT_COLUMN_WIDTH }}
                  >
                    <span className="app-text-control-sm text-app-ink">
                      {t(SOURCE_LABEL_KEYS[group.source])}
                    </span>
                    <span className="app-text-caption text-app-ink/45">
                      {sourceCountLabel(group.items.length, t)}
                    </span>
                  </div>
                  <div
                    className="relative h-10"
                    style={{ width: timelineWidth }}
                  >
                    <div className="absolute inset-0 flex">
                      {gridBackground}
                    </div>
                    {todayLeft !== null ? (
                      <div
                        aria-label={t('planner.timeline.todayMarker')}
                        className="absolute top-0 bottom-0 w-px bg-app-accent"
                        style={{ left: todayLeft }}
                      />
                    ) : null}
                  </div>
                </div>

                {group.items.map((item) => {
                  const metadata = item.event.metadata;
                  const metaParts = [
                    formatItemTime(item, formatters),
                    item.event.workspace?.name,
                    metadata.location,
                    metadata.taskListKey && metadata.taskNumber
                      ? `${metadata.taskListKey}-${metadata.taskNumber}`
                      : null,
                    metadata.status,
                    metadata.attendeeCount !== null &&
                    metadata.attendeeCount !== undefined
                      ? t('planner.timeline.attendeeCount', {
                          count: metadata.attendeeCount,
                        })
                      : null,
                  ].filter((part): part is string => Boolean(part));
                  const barStyle: CSSProperties = {
                    left: item.left,
                    width: item.width,
                    backgroundColor: item.event.color,
                  };

                  return (
                    <button
                      key={item.event.id}
                      type="button"
                      onClick={() => onEventClick(item.event)}
                      aria-label={t('planner.timeline.openItem', {
                        title: item.event.title,
                      })}
                      className="group flex w-full border-b border-app-border text-left transition-colors hover:bg-app-surface-hover"
                    >
                      <div
                        className="sticky left-0 z-10 flex min-h-14 shrink-0 items-center gap-3 border-r border-app-border bg-app-bg px-4 py-2 group-hover:bg-app-surface-hover"
                        style={{ width: LEFT_COLUMN_WIDTH }}
                      >
                        <span
                          className="size-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: item.event.color }}
                        />
                        <span className="min-w-0 flex-1">
                          <span
                            className="app-text-body-sm block truncate font-medium text-app-ink"
                            title={item.event.title}
                          >
                            {item.event.title}
                          </span>
                          <span className="app-text-caption mt-0.5 block truncate text-app-ink/45">
                            {metaParts.join(' · ')}
                          </span>
                        </span>
                      </div>
                      <div
                        className="relative min-h-14"
                        style={{ width: timelineWidth }}
                      >
                        <div className="absolute inset-0 flex">
                          {gridBackground}
                        </div>
                        {todayLeft !== null ? (
                          <div
                            className="absolute top-0 bottom-0 w-px bg-app-accent/80"
                            style={{ left: todayLeft }}
                          />
                        ) : null}
                        <div
                          className={cn(
                            'app-text-micro absolute top-1/2 flex h-6 -translate-y-1/2 items-center overflow-hidden px-2 font-semibold text-white shadow-sm',
                            item.clippedStart ? 'rounded-r-md' : 'rounded-l-md',
                            item.clippedEnd ? 'rounded-l-md' : 'rounded-r-md',
                          )}
                          style={barStyle}
                          title={item.event.title}
                        >
                          <span className="truncate">{item.event.title}</span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
