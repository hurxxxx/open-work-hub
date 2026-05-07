import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { DataTable, Panel, StatusBadge, type DataTableColumn } from '@ai-do/ui';

type PlmRow = {
  template: string;
  scope: string;
  lastRun: string;
};

export function PlmPreview() {
  const { t } = useTranslation('apps');
  const rows = useMemo<PlmRow[]>(
    () => [
      { template: t('plm.preview.ecoByProject'), scope: 'Project A', lastRun: t('plm.preview.threeMinutesAgo') },
      { template: t('plm.preview.bomStatusSnapshot'), scope: 'Engineering', lastRun: t('plm.preview.twelveMinutesAgo') },
    ],
    [t],
  );
  const columns = useMemo<DataTableColumn<PlmRow>[]>(
    () => [
      { accessorKey: 'template', header: t('plm.preview.columns.template') },
      { accessorKey: 'scope', header: t('plm.preview.columns.scope') },
      { accessorKey: 'lastRun', header: t('plm.preview.columns.lastRun') },
    ],
    [t],
  );
  return (
    <Panel
      eyebrow="PLM"
      title={t('plm.preview.title')}
      status={<StatusBadge>{t('plm.preview.safePreview')}</StatusBadge>}
    >
      <DataTable columns={columns} rows={rows} />
    </Panel>
  );
}
