import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface EmptyStateProps {
  children: ReactNode;
  greeting?: string;
  subline?: string;
}

export function EmptyState({
  children,
  greeting,
  subline,
}: EmptyStateProps) {
  const { t } = useTranslation('apps');

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-app-bg">
      <div className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="text-center">
          <h2 className="app-text-title-lg text-app-ink">{greeting ?? t('ai.emptyGreeting')}</h2>
          <p className="mt-1 app-text-body-sm text-app-ink/55 dark:text-app-ink/65">
            {subline ?? t('ai.emptySubline')}
          </p>
        </div>
      </div>
      <div className="sticky bottom-0 z-10 border-t border-app-border bg-app-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
        <div className="mx-auto w-full max-w-2xl">{children}</div>
      </div>
    </div>
  );
}
