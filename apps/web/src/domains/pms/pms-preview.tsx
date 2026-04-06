import { LineChartCard, MetricInline, Panel, StatusBadge } from '@aidoo/ui';

const pmsMetrics = [
  { label: 'Issue triage', value: '3 open · owner reassignment ready' },
  { label: 'Task updates', value: '2 blocked · preview generated' },
  { label: 'Release notes', value: 'draft linked to source tasks' },
];

export function PmsPreview() {
  return (
    <div className="grid gap-5">
      <Panel
        eyebrow="PMS"
        title="프로젝트 운영 스냅샷"
        description="프로젝트 진행률, 이슈 처리량, 최근 운영 신호를 PMS 작업면으로 보내기 전에 빠르게 훑는 요약 카드입니다."
        status={<StatusBadge>live shell</StatusBadge>}
      >
        <div className="grid gap-4">
          {pmsMetrics.map((metric) => (
            <MetricInline key={metric.label} label={metric.label} value={metric.value} />
          ))}
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
