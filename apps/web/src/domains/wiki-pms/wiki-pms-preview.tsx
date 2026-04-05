import { LineChartCard, MetricInline, Panel, StatusBadge } from '@aidoo/ui';

export function WikiPmsPreview() {
  return (
    <div className="grid gap-5">
      <Panel
        eyebrow="Wiki / PMS"
        title="할당 작업"
        status={<StatusBadge>preview only</StatusBadge>}
      >
        <div className="grid gap-4">
          <MetricInline label="Issue triage" value="3 open · owner reassignment ready" />
          <MetricInline label="Wiki summary" value="2 pages updated today" />
          <MetricInline label="Release notes" value="draft linked to source pages" />
        </div>
      </Panel>
      <LineChartCard
        title="Issue throughput"
        categories={['Mon', 'Tue', 'Wed', 'Thu', 'Fri']}
        series={[
          {
            key: 'resolved',
            label: 'Resolved',
            color: '#1f2d38',
            data: [3, 5, 4, 6, 5],
          },
        ]}
      />
    </div>
  );
}
