import { useTranslation } from 'react-i18next';
import { InlineNotice } from '@ai-do/ui/feedback/inline-notice';

export function NotFoundView({
  title,
  description,
}: {
  title?: string;
  description?: string;
}) {
  const { t } = useTranslation('auth');
  return (
    <div className="p-6">
      <div className="rounded-xl border border-app-border bg-app-surface-sidebar p-6">
        <h2 className="app-text-title-md mb-2 text-app-ink">
          {title ?? t('notFound.title')}
        </h2>
        <p className="app-text-body mb-4 text-app-ink/55">
          {description ?? t('notFound.description')}
        </p>
        <InlineNotice tone="info">{t('notFound.hint')}</InlineNotice>
      </div>
    </div>
  );
}
