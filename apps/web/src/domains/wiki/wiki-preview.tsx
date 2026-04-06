import { MetricInline, Panel, StatusBadge } from '@aidoo/ui';

const wikiMetrics = [
  { label: 'Wiki summary', value: '2 pages updated today' },
  { label: 'Draft proposal', value: 'release policy preview ready' },
  { label: 'Citations', value: '3 linked source sections' },
];

export function WikiPreview() {
  return (
    <Panel
      eyebrow="Wiki"
      title="문서 초안과 요약"
      description="문서 요약, 개정 초안, 근거 인용을 preview-first 방식으로 다루는 작업면입니다."
      status={<StatusBadge>preview only</StatusBadge>}
    >
      <div className="grid gap-4">
        {wikiMetrics.map((metric) => (
          <MetricInline key={metric.label} label={metric.label} value={metric.value} />
        ))}
      </div>
    </Panel>
  );
}
