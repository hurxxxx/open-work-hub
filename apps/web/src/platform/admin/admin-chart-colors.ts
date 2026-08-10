export const ADMIN_CHART_COLORS = {
  primary: 'var(--ui-color-chart-1)',
  success: 'var(--ui-color-chart-2)',
  accent: 'var(--ui-color-chart-3)',
  warning: 'var(--ui-color-chart-4)',
  danger: 'var(--ui-color-chart-5)',
  muted: 'var(--ui-color-chart-6)',
} as const;

export const ADMIN_CHART_SERIES_COLORS = [
  ADMIN_CHART_COLORS.primary,
  ADMIN_CHART_COLORS.success,
  ADMIN_CHART_COLORS.accent,
  ADMIN_CHART_COLORS.warning,
  ADMIN_CHART_COLORS.danger,
  ADMIN_CHART_COLORS.muted,
] as const;
