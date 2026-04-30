import { DataTable, Panel, StatusBadge, type DataTableColumn } from '@aidoo/ui';

type PlmRow = {
  template: string;
  scope: string;
  lastRun: string;
};

const rows: PlmRow[] = [
  { template: 'ECO by project', scope: 'Project A', lastRun: '3 min ago' },
  { template: 'BOM status snapshot', scope: 'Engineering', lastRun: '12 min ago' },
];

const columns: DataTableColumn<PlmRow>[] = [
  { accessorKey: 'template', header: 'Template' },
  { accessorKey: 'scope', header: 'Scope' },
  { accessorKey: 'lastRun', header: 'Last run' },
];

export function PlmPreview() {
  return (
    <Panel
      eyebrow="PLM"
      title="승인된 조회 템플릿"
      status={<StatusBadge>safe preview</StatusBadge>}
    >
      <DataTable columns={columns} rows={rows} />
    </Panel>
  );
}
