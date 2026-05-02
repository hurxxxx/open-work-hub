import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';

export interface ChatScopeOption {
  id: string;
  title: string;
}

interface ChatScopePickerProps {
  options: ChatScopeOption[];
  /**
   * Selected app ids. ``null`` means "all available" (default behavior on the
   * server). An empty array means "no tools — text only". A populated array
   * narrows the chatbot's reachable tool surface for the next turn.
   */
  selected: string[] | null;
  onChange: (next: string[] | null) => void;
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
        containerRef.current
        && !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    window.addEventListener('mousedown', onClickOutside);
    return () => window.removeEventListener('mousedown', onClickOutside);
  }, [open]);

  const knownIds = useMemo(() => new Set(options.map((item) => item.id)), [options]);
  // Strip ids that disappeared from entitlements so a stale localStorage
  // selection can't reference apps the user no longer has access to.
  const sanitized = useMemo(() => {
    if (selected === null) return null;
    return selected.filter((id) => knownIds.has(id));
  }, [knownIds, selected]);

  const summary = useMemo(() => {
    if (sanitized === null) return t('apps:ai.scope.all');
    if (sanitized.length === 0) return t('apps:ai.scope.toolsNone');
    if (sanitized.length === options.length) return t('apps:ai.scope.all');
    if (sanitized.length === 1) {
      const match = options.find((item) => item.id === sanitized[0]);
      return match ? t(`shell:apps.${match.id}`, { defaultValue: match.title }) : sanitized[0];
    }
    return t('apps:ai.scope.countSelected', { count: sanitized.length });
  }, [options, sanitized, t]);

  const toggle = useCallback(
    (id: string) => {
      const base = sanitized ?? options.map((item) => item.id);
      const next = base.includes(id)
        ? base.filter((item) => item !== id)
        : [...base, id];
      // Collapse "all selected" back to ``null`` so the server falls through
      // to its default-all behavior — keeps the request payload minimal.
      if (next.length === options.length) {
        onChange(null);
      } else {
        onChange(next);
      }
    },
    [onChange, options, sanitized],
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
          className={cn('shrink-0 text-gray-500 transition-transform', open && 'rotate-180')}
        />
      </button>

      {open ? (
        <div className="absolute bottom-full left-0 z-30 mb-2 w-64 rounded-xl border border-app-border bg-app-surface p-2 shadow-lg">
          <div className="mb-2 flex items-center justify-between border-b border-app-border pb-2">
            <span className="app-text-caption text-gray-500">{t('apps:ai.scope.appContext')}</span>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={selectAll}
                className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-gray-500 hover:bg-app-surface-hover"
              >
                {t('apps:ai.scope.all')}
              </button>
              <button
                type="button"
                onClick={selectNone}
                className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-gray-500 hover:bg-app-surface-hover"
              >
                {t('apps:ai.scope.clear')}
              </button>
            </div>
          </div>
          <ul className="space-y-0.5">
            {options.map((item) => {
              const isChecked
                = sanitized === null || sanitized.includes(item.id);
              return (
                <li key={item.id}>
                  <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-app-surface-hover">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggle(item.id)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="app-text-control-sm text-app-ink">
                      {t(`shell:apps.${item.id}`, { defaultValue: item.title })}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 border-t border-app-border pt-2 app-text-micro text-gray-500">
            {t('apps:ai.scope.description')}
          </p>
        </div>
      ) : null}
    </div>
  );
}
