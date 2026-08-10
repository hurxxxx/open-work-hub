import { TemplateCard } from './TemplateCard';
import type { TemplatePreset } from './template-presets';

interface TemplateGridProps {
  templates: TemplatePreset[];
  selectedId?: string | null;
  onPick: (template: TemplatePreset) => void;
  onRemove?: (template: TemplatePreset) => void;
  removingIds?: ReadonlySet<string>;
  removeLabel?: string;
}

export function TemplateGrid({
  templates,
  selectedId,
  onPick,
  onRemove,
  removingIds,
  removeLabel,
}: TemplateGridProps) {
  if (templates.length === 0) return null;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {templates.map((template) => (
        <TemplateCard
          key={template.id}
          template={template}
          selected={selectedId === template.id}
          onPick={() => onPick(template)}
          onRemove={onRemove ? () => onRemove(template) : undefined}
          removeBusy={removingIds?.has(template.id) ?? false}
          removeLabel={removeLabel}
        />
      ))}
    </div>
  );
}
