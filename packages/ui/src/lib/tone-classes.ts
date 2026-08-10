export const uiToneClasses = {
  neutral:
    'border-[var(--ui-color-border)] bg-ui-surface-subtle text-[var(--ui-color-ink-muted)]',
  accent:
    'border-[var(--ui-color-border)] bg-ui-accent-weak text-[var(--ui-color-accent)]',
  success:
    'border-transparent bg-[color-mix(in_oklab,var(--ui-color-success)_12%,white)] text-[var(--ui-color-success)]',
  warning:
    'border-transparent bg-[color-mix(in_oklab,var(--ui-color-warning)_14%,white)] text-[var(--ui-color-warning)]',
  danger:
    'border-transparent bg-[color-mix(in_oklab,var(--ui-color-danger)_14%,white)] text-[var(--ui-color-danger)]',
  inverse: 'border-white/10 bg-white/6 text-white/76',
} as const;
