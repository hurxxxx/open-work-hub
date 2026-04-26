import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Sparkles } from 'lucide-react';

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

const ALL_LABEL = '전체';
const TEXT_ONLY_LABEL = '도구 없음';

export function ChatScopePicker({
  options,
  selected,
  onChange,
  disabled,
}: ChatScopePickerProps) {
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
    if (sanitized === null) return ALL_LABEL;
    if (sanitized.length === 0) return TEXT_ONLY_LABEL;
    if (sanitized.length === options.length) return ALL_LABEL;
    if (sanitized.length === 1) {
      const match = options.find((item) => item.id === sanitized[0]);
      return match?.title ?? sanitized[0];
    }
    return `${sanitized.length}개 선택`;
  }, [options, sanitized]);

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
        aria-label="챗봇이 사용할 앱 컨텍스트 선택"
        title="챗봇이 사용할 앱 컨텍스트"
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
            <span className="app-text-caption text-gray-500">앱 컨텍스트</span>
            <div className="flex gap-1">
              <button
                type="button"
                onClick={selectAll}
                className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-gray-500 hover:bg-app-surface-hover"
              >
                전체
              </button>
              <button
                type="button"
                onClick={selectNone}
                className="app-text-micro rounded border border-app-border px-1.5 py-0.5 text-gray-500 hover:bg-app-surface-hover"
              >
                해제
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
                      {item.title}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 border-t border-app-border pt-2 app-text-micro text-gray-500">
            선택된 앱의 도구만 LLM이 호출할 수 있습니다. 권한은 서버에서
            한 번 더 검사되므로 이 설정으로 권한이 늘어나지는 않습니다.
          </p>
        </div>
      ) : null}
    </div>
  );
}
