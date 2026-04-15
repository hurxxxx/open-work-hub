// UnifiedCalendar — production wrapper around FullCalendar Standard.
//
// Used by:
//   - PlannerView (Phase 3.1)
//   - MeetingView Calendar tab (Phase 3.2)
//
// Design decisions (per Plan Phase 2 design review):
//   - headerToolbar disabled — host owns the toolbar (Planner toolbar is preserved)
//   - timeZone: 'Asia/Seoul', firstDay: 0 (Sun-first per user pref), weekNumbers ISO, locale ko
//   - Sunday rendered in red (CSS via .fc-day-sun in fullcalendar-theme.css)
//   - selectable + editable + eventDurationEditable
//   - dayMaxEvents: 2 with "+N더" expansion (Korean density per D6)
//   - Source-type colors via CalendarEvent.color (D5)
//   - Korean holidays optionally inject as background events
//
// Styling: theme is applied globally via apps/web/src/styles/fullcalendar-theme.css
// which overrides FullCalendar CSS variables to match the app's design tokens
// (light + dark mode). This component does NOT inline styles.
import { forwardRef, useImperativeHandle, useMemo, useRef } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import listPlugin from '@fullcalendar/list';
import interactionPlugin from '@fullcalendar/interaction';
import luxon3Plugin from '@fullcalendar/luxon3';
import koLocale from '@fullcalendar/core/locales/ko';
import type {
  EventInput,
  EventClickArg,
  DateSelectArg,
  EventDropArg,
} from '@fullcalendar/core';
import type { EventResizeDoneArg } from '@fullcalendar/interaction';

import type { CalendarEvent } from '@/src/domains/calendar/calendar-types';
import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';

export type UnifiedCalendarView =
  | 'dayGridMonth'
  | 'timeGridWeek'
  | 'timeGridDay'
  | 'listWeek';

export interface UnifiedCalendarHandle {
  /** Programmatic view + navigation control for host toolbars. */
  changeView: (view: UnifiedCalendarView) => void;
  today: () => void;
  prev: () => void;
  next: () => void;
  gotoDate: (date: Date | string) => void;
  /** Currently active view name. */
  getCurrentView: () => string | undefined;
}

export interface UnifiedCalendarProps {
  events: CalendarEvent[];
  initialView?: UnifiedCalendarView;
  initialDate?: Date | string;
  /** Fired when user clicks an existing event chip. */
  onEventClick?: (event: CalendarEvent, anchorEl: HTMLElement) => void;
  /** Fired when user drag-selects an empty time range to create a new event. */
  onDateSelect?: (range: { start: Date; end: Date; allDay: boolean }) => void;
  /**
   * Fired when user drags an existing event to a new time slot.
   *
   * ``newStart`` / ``newEnd`` are FullCalendar's ``startStr`` / ``endStr`` —
   * ISO strings already formatted with the calendar's named timezone offset.
   * **Always send these to the backend** rather than re-deriving from the JS
   * ``Date`` object — Date.toISOString() on FullCalendar's named-timezone Date
   * objects produces a value that is offset by the named-zone offset (i.e.
   * 9 hours wrong in KST).
   *
   * Call ``revert()`` to roll back the visual change if the backend save fails.
   */
  onEventDrop?: (
    event: CalendarEvent,
    newStart: string,
    newEnd: string,
    revert: () => void,
  ) => void;
  /**
   * Fired when user drags the bottom edge of an event to resize it.
   * ``newEnd`` is FullCalendar's ``endStr`` (see notes on onEventDrop).
   * Call ``revert()`` to roll back the visual change if the backend save fails.
   */
  onEventResize?: (
    event: CalendarEvent,
    newEnd: string,
    revert: () => void,
  ) => void;
  /** Whether to inject Korean holidays as background events (red). Default true. */
  showKoreanHolidays?: boolean;
  /**
   * Calendar height. Maps to FullCalendar's ``height`` option (CssDimValue):
   *   - ``'auto'`` — fit content (week/day expands to full 24h, no internal scroll)
   *   - ``'100%'`` — fill parent container, internal scrollbar for time grid
   *   - number — fixed px height
   * Default ``'100%'``. Parent must have a deterministic height (e.g. flex-1)
   * for ``'100%'`` to resolve correctly.
   */
  height?: number | string;
  /** Optional className for outer wrapper. */
  className?: string;
}

const PLUGINS = [
  dayGridPlugin,
  timeGridPlugin,
  listPlugin,
  interactionPlugin,
  luxon3Plugin,
];

function calendarEventToFc(event: CalendarEvent): EventInput {
  return {
    id: event.id,
    title: event.title,
    start: event.start,
    end: event.end,
    allDay: event.allDay,
    backgroundColor: event.color,
    borderColor: event.color,
    extendedProps: {
      sourceType: event.sourceType,
      sourceId: event.sourceId,
      metadata: event.metadata,
      // Roundtrip the original CalendarEvent so callbacks can return it
      // without rebuilding from FC's EventApi shape.
      original: event,
    },
  };
}

function buildKoreanHolidayBackgroundEvents(initialDate: Date): EventInput[] {
  // Inject the visible year + the next year so the calendar is correct when the
  // user navigates forward. Cheap (~20 events). Re-derived on initialDate change.
  const events: EventInput[] = [];
  const currentYear = initialDate.getFullYear();
  for (const year of [currentYear, currentYear + 1]) {
    for (let month = 0; month < 12; month++) {
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      for (let day = 1; day <= daysInMonth; day++) {
        const names = getKoreanHolidayNames(year, month, day);
        if (!names) continue;
        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        events.push({
          id: `holiday-${dateStr}`,
          title: names.join(', '),
          start: dateStr,
          allDay: true,
          display: 'background',
          backgroundColor: '#fee2e2', // red-100 — overridden in dark mode via CSS var
          classNames: ['fc-korean-holiday'],
        });
      }
    }
  }
  return events;
}

export const UnifiedCalendar = forwardRef<UnifiedCalendarHandle, UnifiedCalendarProps>(
  function UnifiedCalendar(props, ref) {
    const {
      events,
      initialView = 'dayGridMonth',
      initialDate,
      onEventClick,
      onDateSelect,
      onEventDrop,
      onEventResize,
      showKoreanHolidays = true,
      height = '100%',
      className,
    } = props;

    const calendarRef = useRef<FullCalendar | null>(null);

    useImperativeHandle(
      ref,
      () => ({
        changeView: (view) => calendarRef.current?.getApi().changeView(view),
        today: () => calendarRef.current?.getApi().today(),
        prev: () => calendarRef.current?.getApi().prev(),
        next: () => calendarRef.current?.getApi().next(),
        gotoDate: (date) => calendarRef.current?.getApi().gotoDate(date),
        getCurrentView: () => calendarRef.current?.getApi().view.type,
      }),
      [],
    );

    const fcEvents = useMemo<EventInput[]>(() => {
      const base = events.map(calendarEventToFc);
      if (!showKoreanHolidays) return base;
      const anchor =
        initialDate instanceof Date
          ? initialDate
          : initialDate
            ? new Date(initialDate)
            : new Date();
      return [...base, ...buildKoreanHolidayBackgroundEvents(anchor)];
    }, [events, showKoreanHolidays, initialDate]);

    return (
      <div
        className={`absolute inset-0 ${className ?? ''}`.trim()}
        data-unified-calendar=""
      >
        <FullCalendar
          ref={calendarRef}
          plugins={PLUGINS}
          initialView={initialView}
          initialDate={initialDate}
          timeZone="Asia/Seoul"
          locale={koLocale}
          firstDay={0}
          weekNumbers
          weekNumberCalculation="ISO"
          headerToolbar={false}
          nowIndicator
          dayMaxEvents={2}
          selectable
          editable
          eventDurationEditable
          height={height}
          events={fcEvents}
          select={(arg: DateSelectArg) => {
            onDateSelect?.({ start: arg.start, end: arg.end, allDay: arg.allDay });
          }}
          eventClick={(arg: EventClickArg) => {
            const original = arg.event.extendedProps.original as
              | CalendarEvent
              | undefined;
            if (!original) return;
            onEventClick?.(original, arg.el);
          }}
          eventDrop={(arg: EventDropArg) => {
            const original = arg.event.extendedProps.original as
              | CalendarEvent
              | undefined;
            if (!original || !arg.event.startStr) return;
            onEventDrop?.(
              original,
              arg.event.startStr,
              arg.event.endStr || arg.event.startStr,
              arg.revert,
            );
          }}
          eventResize={(arg: EventResizeDoneArg) => {
            const original = arg.event.extendedProps.original as
              | CalendarEvent
              | undefined;
            if (!original || !arg.event.endStr) return;
            onEventResize?.(original, arg.event.endStr, arg.revert);
          }}
        />
      </div>
    );
  },
);
