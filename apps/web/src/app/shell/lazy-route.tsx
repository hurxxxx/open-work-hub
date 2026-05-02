import { Suspense, type ReactElement } from 'react';
import { useTranslation } from 'react-i18next';

function LazyRouteFallback() {
  const { t } = useTranslation('common');

  return (
    <div
      aria-label={t('feedback.loading')}
      role="status"
      className="flex h-full min-h-32 items-center justify-center text-app-ink/40"
    />
  );
}

export function lazyRoute(element: ReactElement): ReactElement {
  return (
    <Suspense
      fallback={<LazyRouteFallback />}
    >
      {element}
    </Suspense>
  );
}
