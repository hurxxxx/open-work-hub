import { useState } from 'react';
import { Button, Dialog } from '@ai-do/ui';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  STYLES_BY_GROUP,
  STYLE_GROUPS,
  type StyleGroupId,
  type StyleShape,
} from '../style-presets';
import { StyleSwatch } from './StyleSwatch';

interface StylePickerSheetProps {
  open: boolean;
  onClose: () => void;
  selectedChips: string[];
  onChange: (next: string[]) => void;
}

export function StylePickerSheet({
  open,
  onClose,
  selectedChips,
  onChange,
}: StylePickerSheetProps) {
  const { t } = useTranslation('apps');
  const [collapsed, setCollapsed] = useState<Set<StyleGroupId>>(new Set());

  function toggleChip(id: StyleShape) {
    const set = new Set(selectedChips);
    if (set.has(id)) set.delete(id);
    else set.add(id);
    onChange(Array.from(set));
  }

  function toggleGroup(group: StyleGroupId) {
    const next = new Set(collapsed);
    if (next.has(group)) next.delete(group);
    else next.add(group);
    setCollapsed(next);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      closeLabel={t('common:actions.close')}
      title={t('ai.imageWizard.style.sheetTitle')}
      description={t('ai.imageWizard.style.sheetDescription')}
      maxWidth="max-w-3xl"
      actions={
        <div className="flex w-full items-center justify-between">
          <span className="app-text-control-sm text-app-ink/50">
            {t('ai.imageWizard.style.selectedCount', { count: selectedChips.length })}
          </span>
          <Button onClick={onClose}>{t('common:actions.close')}</Button>
        </div>
      }
    >
      <div className="space-y-5">
        {STYLE_GROUPS.map((group) => {
          const isCollapsed = collapsed.has(group);
          const presets = STYLES_BY_GROUP[group];
          return (
            <section key={group} className="space-y-2">
              <button
                type="button"
                onClick={() => toggleGroup(group)}
                className="flex w-full items-center gap-2 app-text-control-sm font-medium text-app-ink/80 hover:text-app-ink"
              >
                {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                <span>{t(`ai.imageWizard.style.groups.${group}`)}</span>
                <span className="app-text-caption text-app-ink/40">({presets.length})</span>
              </button>
              {!isCollapsed ? (
                <div className="flex flex-wrap gap-2">
                  {presets.map((preset) => (
                    <StyleSwatch
                      key={preset.id}
                      preset={preset}
                      selected={selectedChips.includes(preset.id)}
                      onToggle={() => toggleChip(preset.id)}
                    />
                  ))}
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    </Dialog>
  );
}

export default StylePickerSheet;
