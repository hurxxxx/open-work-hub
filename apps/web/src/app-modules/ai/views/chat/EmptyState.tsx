import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface EmptyStateProps {
  composer: ReactNode;
  greeting?: string;
  subline?: string;
}

export function EmptyState({
  composer,
  greeting,
  subline,
}: EmptyStateProps) {
  const { t } = useTranslation('apps');

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-10">
      <div className="w-full max-w-2xl space-y-6">
        <div className="text-center">
          <h2 className="app-text-title-lg text-app-ink">{greeting ?? t('ai.emptyGreeting')}</h2>
          <p className="mt-1 app-text-body-sm text-gray-500 dark:text-gray-400">
            {subline ?? t('ai.emptySubline')}
          </p>
        </div>
        {composer}
      </div>
    </div>
  );
}
