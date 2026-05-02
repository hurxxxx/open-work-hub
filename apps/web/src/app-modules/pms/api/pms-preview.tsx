import { MetricInline, Panel, StatusBadge } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';

const pmsMetrics = [
  { labelKey: 'pms.preview.issueTriage', valueKey: 'pms.preview.issueTriageValue' },
  { labelKey: 'pms.preview.taskUpdates', valueKey: 'pms.preview.taskUpdatesValue' },
  { labelKey: 'pms.preview.releaseNotes', valueKey: 'pms.preview.releaseNotesValue' },
];

export function PmsPreview() {
  const { t } = useTranslation('apps');
  return (
    <Panel
      eyebrow="PMS"
      title={t('pms.preview.title')}
      description={t('pms.preview.description')}
      status={<StatusBadge>{t('pms.preview.status')}</StatusBadge>}
    >
      <div className="grid gap-3">
        {pmsMetrics.map((metric) => (
          <MetricInline
            key={metric.labelKey}
            label={t(metric.labelKey)}
            value={t(metric.valueKey)}
          />
        ))}
      </div>
    </Panel>
  );
}
