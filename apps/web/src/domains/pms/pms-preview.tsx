import { MetricInline, Panel, StatusBadge } from '@aidoo/ui';

const pmsMetrics = [
  { label: 'Issue triage', value: '3 open · owner reassignment ready' },
  { label: 'Task updates', value: '2 blocked · preview generated' },
  { label: 'Release notes', value: 'draft linked to source tasks' },
];

export function PmsPreview() {
  return (
    <Panel
      eyebrow="PMS"
      title="프로젝트 운영 스냅샷"
      description="진행률, 상태 변화, 최근 운영 신호를 요약해서 보여주는 보조 패널입니다."
      status={<StatusBadge>live shell</StatusBadge>}
    >
      <div className="grid gap-3">
        {pmsMetrics.map((metric) => (
          <MetricInline key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>
    </Panel>
  );
}
