export const LABEL_PRESET_COLORS: readonly string[] = [
  '#b45309',
  '#1d4ed8',
  '#0f766e',
  '#7c3aed',
  '#dc2626',
  '#16a34a',
  '#ca8a04',
  '#0284c7',
  '#9333ea',
  '#e11d48',
];

export const PMS_WORKFLOW_DEFAULT_STATUS_COLOR = '#3b82f6';

export const PMS_CALENDAR_STATUS_COLORS: Record<string, string> = {
  canceled: '#ef4444',
  complete: '#16a34a',
  done: '#22c55e',
  in_progress: '#3b82f6',
  review: '#8b5cf6',
  todo: '#9ca3af',
} as const;

export const PMS_CALENDAR_FALLBACK_STATUS_COLOR = '#6b7280';

export const PMS_GANTT_READABLE_TEXT_COLORS = {
  dark: '#111827',
  light: '#ffffff',
} as const;

export const PMS_DEFAULT_LABEL_COLOR = '#1f2d38';
