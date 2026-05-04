import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import type {
  CalendarEvent,
  CalendarSourceType,
} from '@/src/platform/calendar/calendar-types';
import {
  getZonedDateParts,
  parseDateOnlyParts,
} from '@/src/platform/time/time-utils';

const LEFT_COLUMN_WIDTH = 320;
const MS_PER_DAY = 86_400_000;

const SOURCE_ORDER: CalendarSourceType[] = [
  'meeting',
  'pms_block',
  'pms_due',
  'planner_event',
];

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

interface TimelineItem {
  event: CalendarEvent;
  start: Date;
  endExclusive: Date;
  left: number;
  width: number;
  clippedStart: boolean;
  clippedEnd: boolean;
}

function dateOnlyToLocalDate(value: string | null | undefined): Date | null {
  const parts = parseDateOnlyParts(value);
  return parts ? new Date(parts.year, parts.month - 1, parts.day) : null;
}

function startOfLocalDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function addDays(date: Date, days: number): Date {
  const next = startOfLocalDay(date);
  next.setDate(next.getDate() + days);
  return next;
}

function diffDays(left: Date, right: Date): number {
  return Math.round(
    (startOfLocalDay(left).getTime() - startOfLocalDay(right).getTime()) /
      MS_PER_DAY,
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function getBaseDayWidth(totalDays: number): number {
  if (totalDays <= 14) return 64;
  if (totalDays <= 28) return 42;
  if (totalDays <= 56) return 30;
  return 24;
}

function getMaxDayWidth(totalDays: number): number {
  if (totalDays <= 14) return 96;
  if (totalDays <= 28) return 56;
  if (totalDays <= 56) return 36;
  return 28;
}

function getTimelineDayWidth(totalDays: number, viewportWidth: number): number {
  const baseDayWidth = getBaseDayWidth(totalDays);
  const maxDayWidth = getMaxDayWidth(totalDays);
  const availableGridWidth = Math.max(0, viewportWidth - LEFT_COLUMN_WIDTH);
  const fittedDayWidth =
    availableGridWidth > 0 ? Math.floor(availableGridWidth / totalDays) : 0;

  return clamp(
    Math.max(baseDayWidth, fittedDayWidth),
    baseDayWidth,
    maxDayWidth,
  );
}

function toTimelineDate(value: string, timeZone: string): Date | null {
  const dateOnly = dateOnlyToLocalDate(value);
  if (dateOnly) {
    return dateOnly;
  }

  const parts = getZonedDateParts(value, timeZone);
  return parts
    ? new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute)
    : null;
}

function buildDays(rangeStart: Date, totalDays: number): Date[] {
  return Array.from({ length: totalDays }, (_, index) =>
    addDays(rangeStart, index),
  );
}

function buildMonthSpans(days: Date[], locale: string) {
  const formatter = new Intl.DateTimeFormat(locale, {
    month: 'long',
    year: 'numeric',
  });
  const spans: Array<{ key: string; label: string; days: number }> = [];

  for (const day of days) {
    const key = `${day.getFullYear()}-${day.getMonth()}`;
    const current = spans.at(-1);
    if (current?.key === key) {
      current.days += 1;
    } else {
      spans.push({ key, label: formatter.format(day), days: 1 });
    }
  }

  return spans;
}

function buildTimelineItems(
  events: CalendarEvent[],
  rangeStart: Date,
  rangeEnd: Date,
  timeZone: string,
  dayWidth: number,
): TimelineItem[] {
  const totalDays = Math.max(1, diffDays(rangeEnd, rangeStart));

  return events
    .map((event) => {
      const start = toTimelineDate(event.start, timeZone);
      const rawEnd = toTimelineDate(event.end, timeZone);
      if (!start || !rawEnd) {
        return null;
      }

      const endExclusive = event.allDay ? rawEnd : addDays(rawEnd, 1);
      const startOffset = diffDays(start, rangeStart);
      const endOffset = Math.max(
        startOffset + 1,
        diffDays(endExclusive, rangeStart),
      );
      const visibleStart = clamp(startOffset, 0, totalDays);
      const visibleEnd = clamp(endOffset, 0, totalDays);
      const width = Math.max(
        dayWidth * 0.6,
        (visibleEnd - visibleStart) * dayWidth,
      );

      return {
        event,
        start,
        endExclusive,
        left: visibleStart * dayWidth,
        width,
        clippedStart: startOffset < 0,
        clippedEnd: endOffset > totalDays,
      };
    })
    .filter((item): item is TimelineItem => item !== null)
    .sort((left, right) => {
      const byStart = left.start.getTime() - right.start.getTime();
      return byStart || left.event.title.localeCompare(right.event.title);
    });
}

function formatDayLabel(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { day: 'numeric' }).format(date);
}

function formatWeekday(date: Date, locale: string): string {
  return new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(date);
}

function formatItemTime(
  item: TimelineItem,
  locale: string,
  timeZone: string,
): string {
  const dateFormatter = new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    timeZone,
  });
  const timeFormatter = new Intl.DateTimeFormat(locale, {
    hour: 'numeric',
    minute: '2-digit',
    timeZone,
  });

  if (item.event.allDay) {
    const endVisible = addDays(item.endExclusive, -1);
    if (diffDays(endVisible, item.start) <= 0) {
      return dateFormatter.format(item.start);
    }
    return `${dateFormatter.format(item.start)} - ${dateFormatter.format(endVisible)}`;
  }

  return `${dateFormatter.format(item.start)} ${timeFormatter.format(item.start)}`;
}

function sourceCountLabel(
  count: number,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  return t('planner.timeline.itemCount', { count });
}

export function PlannerTimelineView({
  events,
  rangeStart,
  rangeEnd,
  locale,
  timeZone,
  onEventClick,
}: PlannerTimelineViewProps) {
  const { t } = useTranslation('apps');
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewportWidth, setViewportWidth] = useState(0);
  const rangeStartDate =
    dateOnlyToLocalDate(rangeStart) ?? startOfLocalDay(new Date());
  const rangeEndDate =
    dateOnlyToLocalDate(rangeEnd) ?? addDays(rangeStartDate, 1);
  const totalDays = Math.max(1, diffDays(rangeEndDate, rangeStartDate));
  const dayWidth = getTimelineDayWidth(totalDays, viewportWidth);
  const timelineWidth = totalDays * dayWidth;

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }

    const updateWidth = () => setViewportWidth(element.clientWidth);
    updateWidth();

    if (typeof ResizeObserver === 'undefined') {
      return;
    }

    const resizeObserver = new ResizeObserver(updateWidth);
    resizeObserver.observe(element);
    return () => resizeObserver.disconnect();
  }, []);

  const days = useMemo(
    () => buildDays(rangeStartDate, totalDays),
    [rangeStartDate, totalDays],
  );
  const monthSpans = useMemo(
    () => buildMonthSpans(days, locale),
    [days, locale],
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
  const groupedItems = useMemo(
    () =>
      SOURCE_ORDER.map((source) => ({
        source,
        items: items.filter((item) => item.event.sourceType === source),
      })).filter((group) => group.items.length > 0),
    [items],
  );
  const sourceCounts = useMemo(
    () =>
      SOURCE_ORDER.map((source) => ({
        source,
        count: items.filter((item) => item.event.sourceType === source).length,
        color: items.find((item) => item.event.sourceType === source)?.event
          .color,
      })).filter((item) => item.count > 0),
    [items],
  );
  const todayOffset = diffDays(startOfLocalDay(new Date()), rangeStartDate);
  const todayLeft =
    todayOffset >= 0 && todayOffset < totalDays
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
                className="h-2 w-2 rounded-full"
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
                      diffDays(day, startOfLocalDay(new Date())) === 0;
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
                            isSunday ? 'text-red-500' : 'text-app-ink/45',
                          )}
                        >
                          {formatWeekday(day, locale)}
                        </span>
                        <span
                          className={cn(
                            'app-text-control-sm tabular-nums',
                            isToday ? 'text-app-accent' : 'text-app-ink',
                          )}
                        >
                          {formatDayLabel(day, locale)}
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
                    formatItemTime(item, locale, timeZone),
                    metadata.location,
                    metadata.taskListKey && metadata.issueNumber
                      ? `${metadata.taskListKey}-${metadata.issueNumber}`
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
                          className="h-2.5 w-2.5 shrink-0 rounded-full"
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
