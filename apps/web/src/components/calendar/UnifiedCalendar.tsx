// UnifiedCalendar — production wrapper around FullCalendar Standard.
//
// Used by:
//   - PlannerView (Phase 3.1)
//   - MeetingView Calendar tab (Phase 3.2)
//
// Design decisions (per Plan Phase 2 design review):
//   - headerToolbar disabled — host owns the toolbar (Planner toolbar is preserved)
//   - user timeZone with KST default, firstDay: 0 (Sun-first per user pref), weekNumbers ISO, locale ko
//   - Sunday rendered in red (CSS via .fc-day-sun in fullcalendar-theme.css)
//   - selectable + editable + eventDurationEditable
//   - dayMaxEvents defaults to 2 with "+N더" expansion (Korean density per D6)
//   - Source-type colors via CalendarEvent.color (D5)
//   - Korean holidays optionally inject as background events
//
// Styling: theme is applied globally via apps/web/src/styles/fullcalendar-theme.css
// which overrides FullCalendar CSS variables to match the app's design tokens
// (light + dark mode). This component does NOT inline styles.
import { useImperativeHandle, useMemo, useRef, type Ref } from 'react';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import listPlugin from '@fullcalendar/list';
import interactionPlugin from '@fullcalendar/interaction';
import luxon3Plugin from '@fullcalendar/luxon3';
import koLocale from '@fullcalendar/core/locales/ko';
import type {
  EventInput,
  EventContentArg,
  EventHoveringArg,
  EventClickArg,
  DateSelectArg,
  DatesSetArg,
  EventDropArg,
} from '@fullcalendar/core';
import type { EventResizeDoneArg } from '@fullcalendar/interaction';

import { DEFAULT_TIME_ZONE, normalizeTimeZone } from '@/src/platform/time/time-utils';
import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';
import {
  buildDateSelectPayload,
  buildDatesSetPayload,
  buildEventDropPayload,
  buildEventResizePayload,
  getCalendarEventOriginal,
  getKoreanHolidayDayClass,
  getKoreanHolidayLabel,
  toFullCalendarEvent,
} from './unified-calendar-adapter';

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
  /** Fired when the calendar's visible range or active date changes. */
  onDatesSet?: (state: {
    view: UnifiedCalendarView;
    currentDate: Date;
    rangeStart: Date;
    rangeEnd: Date;
  }) => void;
  /** Fired when user clicks an existing event chip. */
  onEventClick?: (event: CalendarEvent, anchorEl: HTMLElement) => void;
  /** Fired when the pointer enters an existing event chip. */
  onEventMouseEnter?: (event: CalendarEvent, anchorEl: HTMLElement) => void;
  /** Fired when the pointer leaves an existing event chip. */
  onEventMouseLeave?: (event: CalendarEvent, anchorEl: HTMLElement) => void;
  /** Fired when user drag-selects an empty time range to create a new event.
   *  ``anchor`` carries the pointer coordinates from the select gesture so the
   *  host can position a popover near the click. */
  onDateSelect?: (range: {
    start: Date;
    end: Date;
    allDay: boolean;
    anchor: { x: number; y: number } | null;
  }) => void;
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
    newAllDay: boolean,
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
   * Month-view overflow behavior. Default ``2`` preserves Planner density with
   * FullCalendar's "+N더" link. Pass ``false`` for views that should grow rows
   * and show every event.
   */
  dayMaxEvents?: boolean | number;
  /** Optional source-specific class names for FullCalendar event elements. */
  eventClassNames?: (event: CalendarEvent) => string[];
  /** IANA timezone used by FullCalendar. Defaults to Korea Standard Time. */
  timeZone?: string;
  /**
   * Calendar height. Maps to FullCalendar's ``height`` option (CssDimValue):
   *   - ``'auto'`` — fit content (week/day expands to full 24h, no internal scroll)
   *   - ``'100%'`` — fill parent container, internal scrollbar for time grid
   *   - number — fixed px height
   * Default ``'100%'``. Parent must have a deterministic height (e.g. flex-1)
   * for ``'100%'`` to resolve correctly.
   */
  height?: number | string;
  /**
   * Wrapper layout. ``fill`` keeps legacy absolute positioning for Planner.
   * ``content`` lets the calendar own its height and grow inside a scroll area.
   */
  layout?: 'fill' | 'content';
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

export function UnifiedCalendar({
  events,
  initialView = 'dayGridMonth',
  initialDate,
  onDatesSet,
  onEventClick,
  onEventMouseEnter,
  onEventMouseLeave,
  onDateSelect,
  onEventDrop,
  onEventResize,
  showKoreanHolidays = true,
  dayMaxEvents = 2,
  eventClassNames,
  timeZone = DEFAULT_TIME_ZONE,
  height = '100%',
  layout = 'fill',
  className,
  ref,
}: UnifiedCalendarProps & { ref?: Ref<UnifiedCalendarHandle> }) {
    const resolvedTimeZone = normalizeTimeZone(timeZone);

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

    const fcEvents = useMemo<EventInput[]>(
      () => events.map(toFullCalendarEvent),
      [events],
    );
    const wrapperClassName = [
      layout === 'fill' ? 'absolute inset-0' : 'relative min-h-full',
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div
        className={wrapperClassName}
        data-unified-calendar=""
      >
        <FullCalendar
          ref={calendarRef}
          plugins={PLUGINS}
          initialView={initialView}
          initialDate={initialDate}
          timeZone={resolvedTimeZone}
          locale={koLocale}
          firstDay={0}
          weekNumbers
          weekNumberCalculation="ISO"
          headerToolbar={false}
          nowIndicator
          dayMaxEvents={dayMaxEvents}
          selectable={Boolean(onDateSelect)}
          editable={Boolean(onEventDrop || onEventResize)}
          eventDurationEditable={Boolean(onEventResize)}
          height={height}
          events={fcEvents}
          eventClassNames={
            eventClassNames
              ? (arg: EventContentArg) => {
                  const original = getCalendarEventOriginal(arg.event);
                  return original ? eventClassNames(original) : [];
                }
              : undefined
          }
          eventMouseEnter={(arg: EventHoveringArg) => {
            const original = getCalendarEventOriginal(arg.event);
            if (!original) return;
            onEventMouseEnter?.(original, arg.el);
          }}
          eventMouseLeave={(arg: EventHoveringArg) => {
            const original = getCalendarEventOriginal(arg.event);
            if (!original) return;
            onEventMouseLeave?.(original, arg.el);
          }}
          datesSet={(arg: DatesSetArg) => {
            const payload = buildDatesSetPayload(arg);
            onDatesSet?.({
              view: payload.view as UnifiedCalendarView,
              currentDate: payload.currentDate,
              rangeStart: payload.rangeStart,
              rangeEnd: payload.rangeEnd,
            });
          }}
          dayCellClassNames={
            showKoreanHolidays
              ? (arg) => getKoreanHolidayDayClass(arg.date)
              : undefined
          }
          dayCellDidMount={
            showKoreanHolidays
              ? (arg) => {
                  const labelText = getKoreanHolidayLabel(arg.date);
                  if (!labelText) return;
                  // Inject the holiday label as a sibling of the day-top area
                  // (inside the day frame) so it flows as its own block line
                  // below the date number rather than being squeezed into the
                  // tiny flex row next to the date. Month view only — week/day
                  // cells don't have `.fc-daygrid-day-frame`.
                  const frame = arg.el.querySelector('.fc-daygrid-day-frame');
                  if (!frame) return;
                  if (frame.querySelector('.fc-korean-holiday-label')) return;
                  const top = frame.querySelector('.fc-daygrid-day-top');
                  const label = document.createElement('div');
                  label.className = 'fc-korean-holiday-label';
                  label.textContent = labelText;
                  if (top && top.nextSibling) {
                    frame.insertBefore(label, top.nextSibling);
                  } else {
                    frame.appendChild(label);
                  }
                }
              : undefined
          }
          select={(arg: DateSelectArg) => {
            onDateSelect?.(buildDateSelectPayload(arg));
          }}
          eventClick={(arg: EventClickArg) => {
            const original = getCalendarEventOriginal(arg.event);
            if (!original) return;
            onEventClick?.(original, arg.el);
          }}
          eventDrop={(arg: EventDropArg) => {
            const payload = buildEventDropPayload(arg);
            if (!payload) return;
            onEventDrop?.(
              payload.event,
              payload.newStart,
              payload.newEnd,
              payload.newAllDay,
              payload.revert,
            );
          }}
          eventResize={(arg: EventResizeDoneArg) => {
            const payload = buildEventResizePayload(arg);
            if (!payload) return;
            onEventResize?.(payload.event, payload.newEnd, payload.revert);
          }}
        />
      </div>
    );
}
