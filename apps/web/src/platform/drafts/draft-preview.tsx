import { useTranslation } from 'react-i18next';

import { Button, MetricInline, Panel } from '@ai-do/ui';

export function DraftPreview() {
  const { t } = useTranslation('apps');
  return (
    <Panel
      eyebrow={t('drafts.preview.eyebrow')}
      title={t('drafts.preview.title')}
      actions={<Button variant="secondary">{t('drafts.preview.viewTemplates')}</Button>}
    >
      <div className="grid gap-3">
        <MetricInline label={t('drafts.preview.projectSummary')} value={t('drafts.preview.projectSummaryValue')} />
        <MetricInline label={t('drafts.preview.riskReview')} value={t('drafts.preview.riskReviewValue')} />
        <MetricInline label={t('drafts.preview.exportQueue')} value={t('drafts.preview.exportQueueValue')} />
      </div>
    </Panel>
  );
}
