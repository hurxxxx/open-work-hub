import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import {
  isChatScopeOptionSelected,
  resolveChatScopePickerModel,
  toggleChatScopeSelection,
  type ChatScopeOption,
  type ChatScopeSelection,
} from './chat-scope-picker-model';

export type {
  ChatScopeOption,
  ChatScopeSelection,
} from './chat-scope-picker-model';

interface ChatScopePickerProps {
  options: ChatScopeOption[];
  selected: ChatScopeSelection;
  onChange: (next: ChatScopeSelection) => void;
  disabled?: boolean;
}

export function ChatScopePicker({
  options,
  selected,
  onChange,
  disabled,
}: ChatScopePickerProps) {
  const { t } = useTranslation(['apps', 'shell']);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    window.addEventListener('mousedown', onClickOutside);
    return () => window.removeEventListener('mousedown', onClickOutside);
  }, [open]);

  const model = useMemo(
    () => resolveChatScopePickerModel({ options, selected }),
    [options, selected],
  );

  const summary = useMemo(() => {
    if (model.summary.kind === 'all') return t('apps:ai.scope.all');
    if (model.summary.kind === 'none') return t('apps:ai.scope.toolsNone');
    if (model.summary.kind === 'single') {
      const { id, option } = model.summary;
      return option
        ? t(`shell:apps.${option.id}`, { defaultValue: option.title })
        : id;
    }
    return t('apps:ai.scope.countSelected', { count: model.summary.count });
  }, [model.summary, t]);

  const toggle = useCallback(
    (id: string) => {
      onChange(toggleChatScopeSelection({ id, options, selected }));
    },
    [onChange, options, selected],
  );

  const selectAll = useCallback(() => onChange(null), [onChange]);
  const selectNone = useCallback(() => onChange([]), [onChange]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          'app-text-control-sm flex h-8 items-center gap-1.5 rounded-full border border-app-border bg-app-surface px-3 text-app-ink transition-colors hover:border-app-accent',
          disabled && 'cursor-not-allowed opacity-60',
        )}
        aria-label={t('apps:ai.scope.selectContext')}
        title={t('apps:ai.scope.title')}
      >
        <Sparkles size={14} className="text-app-accent" />
        <span className="truncate">{summary}</span>
        <ChevronDown
          size={14}
          className={cn(
            'shrink-0 text-app-ink/55 transition-transform',
            open && 'rotate-180',
          )}
        />
      </button>

      {open ? (
        <div className="absolute bottom-full left-0 z-30 mb-2 w-64 rounded-xl border border-app-border bg-app-surface p-2 shadow-lg">
          <div className="mb-2 flex items-center justify-between border-b border-app-border pb-2">
            <span className="app-text-caption text-app-ink/55">
              {t('apps:ai.scope.appContext')}
            </span>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={selectAll}
                className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-app-ink/55 hover:bg-app-surface-hover"
              >
                {t('apps:ai.scope.all')}
              </button>
              <button
                type="button"
                onClick={selectNone}
                className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-app-ink/55 hover:bg-app-surface-hover"
              >
                {t('apps:ai.scope.clear')}
              </button>
            </div>
          </div>
          <ul className="space-y-0.5">
            {options.map((item) => {
              const isChecked = isChatScopeOptionSelected(
                model.selection,
                item.id,
              );
              return (
                <li key={item.id}>
                  <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-app-surface-hover">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggle(item.id)}
                      className="size-3.5"
                    />
                    <span className="app-text-control-sm text-app-ink">
                      {t(`shell:apps.${item.id}`, { defaultValue: item.title })}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 border-t border-app-border pt-2 app-text-micro text-app-ink/55">
            {t('apps:ai.scope.description')}
          </p>
        </div>
      ) : null}
    </div>
  );
}
