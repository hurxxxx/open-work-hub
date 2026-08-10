import { useCallback, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@open-work-hub/ui';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  UnifiedCalendar,
  type UnifiedCalendarHandle,
} from '@/src/components/calendar/UnifiedCalendar';
import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';
import type { PmsTask, PmsTaskListStatus } from '../api/pms-api';
import {
  addCalendarMonths,
  buildPmsCalendarEvents,
  startOfCalendarMonth,
} from './calendar-view-model';
import { formatDate, getStatusLabel } from './pms-constants';

type HoveredCalendarTask = {
  eventId: string;
  rect: {
    bottom: number;
    left: number;
    top: number;
  };
  task: PmsTask;
};

export const CalendarView = ({
  tasks,
  taskListStatuses,
}: {
  tasks: PmsTask[];
  taskListStatuses?: PmsTaskListStatus[];
}) => {
  const { i18n, t } = useTranslation('apps');
  const calendarRef = useRef<UnifiedCalendarHandle | null>(null);
  const [visibleMonth, setVisibleMonth] = useState(() =>
    startOfCalendarMonth(new Date()),
  );
  const [hoveredTask, setHoveredTask] = useState<HoveredCalendarTask | null>(
    null,
  );

  const events = useMemo(
    () => buildPmsCalendarEvents(tasks, taskListStatuses),
    [taskListStatuses, tasks],
  );
  const tasksById = useMemo(
    () => new Map(tasks.map((task) => [task.id, task])),
    [tasks],
  );
  const monthTitle = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        month: 'long',
        year: 'numeric',
      }).format(visibleMonth),
    [i18n.language, visibleMonth],
  );
  const handleEventMouseEnter = useCallback(
    (event: CalendarEvent, anchorEl: HTMLElement) => {
      const task = tasksById.get(event.sourceId);
      if (!task) return;
      const rect = anchorEl.getBoundingClientRect();
      setHoveredTask({
        eventId: event.id,
        rect: {
          bottom: rect.bottom,
          left: rect.left,
          top: rect.top,
        },
        task,
      });
    },
    [tasksById],
  );
  const handleEventMouseLeave = useCallback((event: CalendarEvent) => {
    setHoveredTask((current) =>
      current?.eventId === event.id ? null : current,
    );
  }, []);

  const handleDatesSet = useCallback(
    ({ currentDate }: { currentDate: Date }) => {
      setVisibleMonth(startOfCalendarMonth(currentDate));
      setHoveredTask(null);
    },
    [],
  );
  const shiftVisibleMonth = useCallback(
    (months: number) => {
      calendarRef.current?.gotoDate(addCalendarMonths(visibleMonth, months));
      setHoveredTask(null);
    },
    [visibleMonth],
  );

  return (
    <div className="h-full flex flex-col card p-0 overflow-hidden">
      <div className="flex flex-col gap-2 border-b border-app-border bg-app-surface-sidebar/30 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-1">
          <CalendarDays size={16} className="mr-1 shrink-0 text-app-accent" />
          <Button
            aria-label={t('pms.calendar.previousYear')}
            onClick={() => shiftVisibleMonth(-12)}
            size="icon"
            title={t('pms.calendar.previousYear')}
            variant="ghost"
          >
            <ChevronsLeft aria-hidden="true" size={16} />
          </Button>
          <Button
            aria-label={t('pms.calendar.previousMonth')}
            onClick={() => shiftVisibleMonth(-1)}
            size="icon"
            title={t('pms.calendar.previousMonth')}
            variant="ghost"
          >
            <ChevronLeft aria-hidden="true" size={16} />
          </Button>
          <h3 className="app-text-title-md mx-2 min-w-0 truncate text-app-ink">
            {monthTitle}
          </h3>
          <Button
            aria-label={t('pms.calendar.nextMonth')}
            onClick={() => shiftVisibleMonth(1)}
            size="icon"
            title={t('pms.calendar.nextMonth')}
            variant="ghost"
          >
            <ChevronRight aria-hidden="true" size={16} />
          </Button>
          <Button
            aria-label={t('pms.calendar.nextYear')}
            onClick={() => shiftVisibleMonth(12)}
            size="icon"
            title={t('pms.calendar.nextYear')}
            variant="ghost"
          >
            <ChevronsRight aria-hidden="true" size={16} />
          </Button>
        </div>
        <Button
          onClick={() => calendarRef.current?.today()}
          size="dense"
          variant="secondary"
        >
          {t('pms.calendar.today')}
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <UnifiedCalendar
          ref={calendarRef}
          className="min-h-full"
          dayMaxEvents={false}
          eventClassNames={(event) =>
            event.sourceType === 'pms_due' ? ['fc-pms-task-event'] : []
          }
          events={events}
          height="auto"
          initialDate={visibleMonth}
          initialView="dayGridMonth"
          layout="content"
          onDatesSet={handleDatesSet}
          onEventMouseEnter={handleEventMouseEnter}
          onEventMouseLeave={handleEventMouseLeave}
        />
      </div>
      <CalendarTaskHoverCard
        hoveredTask={hoveredTask}
        taskListStatuses={taskListStatuses}
      />
    </div>
  );
};

function CalendarTaskHoverCard({
  hoveredTask,
  taskListStatuses,
}: {
  hoveredTask: HoveredCalendarTask | null;
  taskListStatuses?: PmsTaskListStatus[];
}) {
  if (!hoveredTask || typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="pointer-events-none fixed z-[1000] w-72 rounded-lg border border-app-border bg-app-bg p-3 text-left shadow-xl"
      role="tooltip"
      style={getHoverCardStyle(hoveredTask.rect)}
    >
      <CalendarTaskDetailCard
        task={hoveredTask.task}
        taskListStatuses={taskListStatuses}
      />
    </div>,
    document.body,
  );
}

function CalendarTaskDetailCard({
  task,
  taskListStatuses,
}: {
  task: PmsTask;
  taskListStatuses?: PmsTaskListStatus[];
}) {
  const { t } = useTranslation('apps');
  const assignee = resolveCalendarTaskAssignee(task);
  const notSet = t('pms.list.notSet');
  const detailRows = [
    {
      label: t('pms.list.status'),
      value: task.status_label || getStatusLabel(task.status, taskListStatuses),
    },
    {
      label: t('pms.filter.priorityLabel'),
      value: task.priority_label || task.priority || notSet,
    },
    {
      label: t('pms.list.assignee'),
      value: assignee || t('pms.taskDetail.unassigned'),
    },
    {
      label: t('pms.filter.startDateLabel'),
      value: formatDate(task.start_date) || notSet,
    },
    {
      label: t('pms.list.dueDate'),
      value: formatDate(task.due_date) || notSet,
    },
  ];

  return (
    <>
      <div className="app-text-micro mb-1 text-app-ink/45">
        {task.reference}
      </div>
      <div className="app-text-body-sm mb-2 line-clamp-2 font-semibold text-app-ink">
        {task.title}
      </div>
      <dl className="space-y-1.5">
        {detailRows.map((row) => (
          <div
            key={row.label}
            className="flex items-start justify-between gap-3"
          >
            <dt className="app-text-micro shrink-0 text-app-ink/50">
              {row.label}
            </dt>
            <dd className="app-text-micro min-w-0 truncate text-right text-app-ink">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function getHoverCardStyle(rect: HoveredCalendarTask['rect']): {
  left: number;
  top: number;
} {
  const margin = 8;
  const width = 288;
  const estimatedHeight = 180;
  const viewportWidth =
    typeof window === 'undefined' ? 1024 : window.innerWidth;
  const viewportHeight =
    typeof window === 'undefined' ? 768 : window.innerHeight;
  const left = Math.min(
    Math.max(rect.left, margin),
    Math.max(margin, viewportWidth - width - margin),
  );
  const below = rect.bottom + margin;
  const top =
    below + estimatedHeight > viewportHeight
      ? Math.max(margin, rect.top - estimatedHeight - margin)
      : below;

  return { left, top };
}

function resolveCalendarTaskAssignee(task: PmsTask): string {
  if (task.assignee_names?.length) {
    return task.assignee_names.join(', ');
  }
  return task.assignee_name ?? '';
}
