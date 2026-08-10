import { i18n } from '@/src/platform/i18n';

export function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--ui-color-bg)] px-6">
      <output
        aria-live="polite"
        className="grid w-full max-w-sm gap-2 rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-5 text-center shadow-[var(--ui-shadow-sm)]"
      >
        <p className="m-0 text-[0.72rem] font-semibold uppercase tracking-[0.1em] text-[var(--ui-color-ink-subtle)]">
          {i18n.t('auth:loading.eyebrow')}
        </p>
        <strong className="text-[1rem] text-[var(--ui-color-ink)]">{i18n.t('auth:loading.title')}</strong>
        <p className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">
          {i18n.t('auth:loading.description')}
        </p>
      </output>
    </div>
  );
}
