import { parseDateOnlyParts } from '@/src/platform/time/time-utils';
import type { PmsTask, PmsTaskListStatus } from '../api/pms-api';
import { PMS_GANTT_READABLE_TEXT_COLORS } from './pms-color-palettes';

const MS_PER_DAY = 86_400_000;

export interface GanttDateRange {
  end: Date;
  start: Date;
}

export type GanttDragMode = 'move' | 'resize-end' | 'resize-start';

export interface GanttDragPreview extends GanttDateRange {
  deltaDays: number;
  mode: GanttDragMode;
  taskId: string;
}

export interface GanttBarStyleInput {
  dayWidth: number;
  dragging: GanttDragPreview | null;
  visibleEnd: Date;
  visibleStart: Date;
  task: Pick<PmsTask, 'due_date' | 'id' | 'start_date'>;
}

export type GanttScheduleOverride = Pick<PmsTask, 'due_date' | 'start_date'>;

export type GanttStatusBarVisualStyle = {
  backgroundColor: string;
  borderColor: string;
  color: string;
};

export function parseGanttDateOnly(
  value: string | null | undefined,
): Date | null {
  const parts = parseDateOnlyParts(value);
  return parts ? new Date(parts.year, parts.month - 1, parts.day) : null;
}

export function toGanttDateOnly(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function addGanttDays(value: Date, days: number): Date {
  return new Date(
    value.getFullYear(),
    value.getMonth(),
    value.getDate() + days,
  );
}

export function diffGanttDays(left: Date, right: Date): number {
  return Math.round((left.getTime() - right.getTime()) / MS_PER_DAY);
}

export function applyGanttScheduleOverride<
  T extends Pick<PmsTask, 'due_date' | 'start_date'>,
>(task: T, override: GanttScheduleOverride | null | undefined): T {
  if (!override) return task;
  return {
    ...task,
    due_date: override.due_date,
    start_date: override.start_date,
  };
}

export function getGanttDragPreviewRange(
  dragging: GanttDragPreview,
): GanttDateRange {
  if (dragging.mode === 'resize-start') {
    const nextStart = addGanttDays(dragging.start, dragging.deltaDays);
    return {
      end: dragging.end,
      start: nextStart > dragging.end ? dragging.end : nextStart,
    };
  }

  if (dragging.mode === 'resize-end') {
    const nextEnd = addGanttDays(dragging.end, dragging.deltaDays);
    return {
      end: nextEnd < dragging.start ? dragging.start : nextEnd,
      start: dragging.start,
    };
  }

  return {
    end: addGanttDays(dragging.end, dragging.deltaDays),
    start: addGanttDays(dragging.start, dragging.deltaDays),
  };
}

export function getGanttTaskDateRange(
  task: Pick<PmsTask, 'due_date' | 'start_date'>,
): GanttDateRange | null {
  const start = parseGanttDateOnly(task.start_date);
  const end = parseGanttDateOnly(task.due_date);
  if (!start && !end) return null;

  const fallback = start ?? end;
  if (!fallback) return null;

  return {
    end: end ?? fallback,
    start: start ?? fallback,
  };
}

export function getGanttBarStyle({
  dayWidth,
  dragging,
  visibleEnd,
  visibleStart,
  task,
}: GanttBarStyleInput): { left: string; width: string } | null {
  const base = getGanttTaskDateRange(task);
  if (!base) return null;

  const preview =
    dragging?.taskId === task.id ? getGanttDragPreviewRange(dragging) : base;

  if (preview.end < visibleStart || preview.start > visibleEnd) return null;

  const barStart = preview.start < visibleStart ? visibleStart : preview.start;
  const barEnd = preview.end > visibleEnd ? visibleEnd : preview.end;
  const startDay = Math.max(0, diffGanttDays(barStart, visibleStart));
  const endDay = Math.max(startDay, diffGanttDays(barEnd, visibleStart));
  const width = Math.max(1, endDay - startDay + 1) * dayWidth;

  return { left: `${startDay * dayWidth}px`, width: `${width}px` };
}

function parseHexColor(
  value: string | null | undefined,
): { blue: number; green: number; red: number } | null {
  if (!value) return null;
  const trimmed = value.trim();
  const shortMatch = /^#([0-9a-f]{3})$/i.exec(trimmed);
  const longMatch = /^#([0-9a-f]{6})$/i.exec(trimmed);
  const hex = shortMatch
    ? shortMatch[1]
        .split('')
        .map((item) => item + item)
        .join('')
    : longMatch?.[1];
  if (!hex) return null;

  return {
    blue: Number.parseInt(hex.slice(4, 6), 16),
    green: Number.parseInt(hex.slice(2, 4), 16),
    red: Number.parseInt(hex.slice(0, 2), 16),
  };
}

function relativeLuminance(channel: number): number {
  const normalized = channel / 255;
  return normalized <= 0.03928
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4;
}

function readableTextColor(color: string): string {
  const rgb = parseHexColor(color);
  if (!rgb) return PMS_GANTT_READABLE_TEXT_COLORS.light;
  const luminance =
    0.2126 * relativeLuminance(rgb.red) +
    0.7152 * relativeLuminance(rgb.green) +
    0.0722 * relativeLuminance(rgb.blue);
  const whiteContrast = 1.05 / (luminance + 0.05);
  const darkContrast = (luminance + 0.05) / 0.05;
  return darkContrast >= whiteContrast
    ? PMS_GANTT_READABLE_TEXT_COLORS.dark
    : PMS_GANTT_READABLE_TEXT_COLORS.light;
}

export function getGanttStatusBarStyle({
  status,
  taskListStatuses,
}: {
  status: string;
  taskListStatuses?: PmsTaskListStatus[];
}): GanttStatusBarVisualStyle | undefined {
  const color = taskListStatuses?.find((item) => item.slug === status)?.color;
  if (!color || !parseHexColor(color)) return undefined;
  return {
    backgroundColor: color,
    borderColor: color,
    color: readableTextColor(color),
  };
}
