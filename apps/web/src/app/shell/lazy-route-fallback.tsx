import { useTranslation } from 'react-i18next';

export function LazyRouteFallback() {
  const { t } = useTranslation('common');

  return (
    <output
      aria-label={t('feedback.loading')}
      className="flex h-full min-h-32 items-center justify-center text-app-ink/40"
    />
  );
}
