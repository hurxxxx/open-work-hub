/** PMS status/priority display constants shared across views. */

import type { PmsTaskListStatus } from '../api/pms-api';
import {
  formatDateOnly,
  formatDateTime,
  parseDateOnlyParts,
} from '@/src/platform/time/time-utils';

const TASK_STATUSES = ['todo', 'in_progress', 'review', 'done', 'complete'] as const;

const STATUS_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> = {
  todo: 'neutral',
  in_progress: 'accent',
  review: 'accent',
  done: 'success',
  canceled: 'danger',
  complete: 'success',
};

const CATEGORY_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> = {
  not_started: 'neutral',
  active: 'accent',
  done: 'success',
  closed: 'success',
};

function findTaskListStatus(
  slug: string,
  taskListStatuses?: PmsTaskListStatus[],
): PmsTaskListStatus | undefined {
  return taskListStatuses?.find((status) => status.slug === slug);
}

function formatFallbackStatusLabel(slug: string): string {
  return slug.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Resolve tone for a status slug, falling back to custom status category */
export function getStatusTone(
  slug: string,
  taskListStatuses?: PmsTaskListStatus[],
): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (STATUS_TONE[slug]) return STATUS_TONE[slug];
  const status = findTaskListStatus(slug, taskListStatuses);
  return status ? (CATEGORY_TONE[status.category] ?? 'neutral') : 'neutral';
}

/** Get ordered status slugs from task list statuses, falling back to defaults */
export function getStatusSlugs(taskListStatuses?: PmsTaskListStatus[]): string[] {
  if (taskListStatuses && taskListStatuses.length > 0) {
    return taskListStatuses.map((status) => status.slug);
  }
  return [...TASK_STATUSES];
}

/** Get status display name */
export function getStatusLabel(slug: string, taskListStatuses?: PmsTaskListStatus[]): string {
  const status = findTaskListStatus(slug, taskListStatuses);
  return status?.name ?? formatFallbackStatusLabel(slug);
}

/** Pick the default status for newly created tasks without reintroducing backlog. */
export function getDefaultTaskStatus(taskListStatuses?: PmsTaskListStatus[]): string {
  const slugs = getStatusSlugs(taskListStatuses);
  if (slugs.includes('todo')) return 'todo';
  return taskListStatuses?.find((status) => status.category === 'active')?.slug ?? slugs[0] ?? 'todo';
}

export const PRIORITY_COLOR: Record<string, string> = {
  critical: 'text-app-danger',
  high: 'text-orange-500',
  medium: 'text-blue-500',
  low: 'text-app-ink/55',
};

/** Generate a compact avatar initial from a full name. */
export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  return Array.from(name.trim())[0]?.toUpperCase() ?? '?';
}

/** Format ISO date string using the user's date display preference. */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return '';
  if (parseDateOnlyParts(isoDate)) {
    return formatDateOnly(isoDate, {
      fallback: isoDate,
    });
  }
  return formatDateTime(isoDate, {
    fallback: isoDate,
  });
}
