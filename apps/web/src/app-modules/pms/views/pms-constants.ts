/** PMS status/priority display constants shared across views. */

import type { PmsTaskListStatus } from '../api/pms-api';
import {
  formatDateOnly,
  formatDateTime,
  parseDateOnlyParts,
} from '@/src/platform/time/time-utils';

export const ISSUE_STATUSES = ['backlog', 'todo', 'in_progress', 'done', 'canceled'] as const;

export const STATUS_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> = {
  backlog: 'neutral',
  todo: 'neutral',
  in_progress: 'accent',
  done: 'success',
  canceled: 'danger',
};

export const STATUS_DOT_COLOR: Record<string, string> = {
  backlog: 'bg-gray-500',
  todo: 'bg-gray-400',
  in_progress: 'bg-blue-500',
  done: 'bg-green-500',
  canceled: 'bg-red-500',
};

const CATEGORY_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'warning' | 'danger'> = {
  backlog: 'neutral',
  active: 'accent',
  done: 'success',
  canceled: 'danger',
};

/** Resolve tone for a status slug, falling back to custom status category */
export function getStatusTone(
  slug: string,
  taskListStatuses?: PmsTaskListStatus[],
): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (STATUS_TONE[slug]) return STATUS_TONE[slug];
  const ps = taskListStatuses?.find(s => s.slug === slug);
  return ps ? (CATEGORY_TONE[ps.category] ?? 'neutral') : 'neutral';
}

/** Resolve dot color for a status slug */
export function getStatusDotColor(slug: string, taskListStatuses?: PmsTaskListStatus[]): string {
  if (STATUS_DOT_COLOR[slug]) return STATUS_DOT_COLOR[slug];
  const ps = taskListStatuses?.find(s => s.slug === slug);
  if (ps) return ''; // will use inline style with ps.color instead
  return 'bg-gray-500';
}

/** Get ordered status slugs from task list statuses, falling back to defaults */
export function getStatusSlugs(taskListStatuses?: PmsTaskListStatus[]): string[] {
  if (taskListStatuses && taskListStatuses.length > 0) {
    return taskListStatuses.map(s => s.slug);
  }
  return [...ISSUE_STATUSES];
}

/** Get status display name */
export function getStatusLabel(slug: string, taskListStatuses?: PmsTaskListStatus[]): string {
  const ps = taskListStatuses?.find(s => s.slug === slug);
  if (ps) return ps.name;
  return slug.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export const PRIORITY_COLOR: Record<string, string> = {
  critical: 'text-red-500',
  high: 'text-orange-500',
  medium: 'text-blue-500',
  low: 'text-gray-500',
};

/** Generate initials from a full name, e.g. "John Doe" → "JD" */
export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  return name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/** Format ISO date string for display, e.g. "2024-04-10" → "Apr 10" */
export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return '';
  if (parseDateOnlyParts(isoDate)) {
    return formatDateOnly(isoDate, {
      fallback: isoDate,
      locale: 'en-US',
      month: 'short',
      day: 'numeric',
    });
  }
  return formatDateTime(isoDate, {
    fallback: isoDate,
    locale: 'en-US',
    month: 'short',
    day: 'numeric',
  });
}
