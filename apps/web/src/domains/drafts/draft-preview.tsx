import { Button, MetricInline, Panel } from '@doowon/ui';

export function DraftPreview() {
  return (
    <Panel
      eyebrow="Drafts"
      title="초안 큐"
      actions={<Button variant="secondary">템플릿 보기</Button>}
    >
      <div className="grid gap-4">
        <MetricInline label="Project A Summary" value="citation blocks ready · review pending" />
        <MetricInline label="Risk Review Memo" value="2 required fields missing" />
        <MetricInline label="Export Queue" value="1 waiting · 1 generated" />
      </div>
    </Panel>
  );
}
