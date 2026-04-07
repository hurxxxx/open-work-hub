/** PMS status/priority display constants shared across views. */

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
  const d = new Date(isoDate);
  if (isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
