import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import { ChevronDown, LayoutGrid, Search } from 'lucide-react';

export interface AccessibleMultiSelectProps {
  allLabel: string;
  buttonLabel: (summary: string) => string;
  label: string;
  noResultsLabel: string;
  onChange: (next: string[]) => void;
  options: string[];
  searchLabel: string;
  searchPlaceholder: string;
  selected: string[];
  selectedText: (count: number) => string;
}

export function AccessibleMultiSelect({
  allLabel,
  buttonLabel,
  label,
  noResultsLabel,
  onChange,
  options,
  searchLabel,
  searchPlaceholder,
  selected,
  selectedText,
}: AccessibleMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const generatedId = useId();
  const labelId = `${generatedId}-label`;
  const panelId = `${generatedId}-panel`;

  const close = useCallback((returnFocus = false) => {
    setOpen(false);
    setQuery('');
    if (returnFocus) {
      window.requestAnimationFrame(() => triggerRef.current?.focus());
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const closeWhenOutside = (event: Event) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener('pointerdown', closeWhenOutside);
    document.addEventListener('focusin', closeWhenOutside);
    return () => {
      document.removeEventListener('pointerdown', closeWhenOutside);
      document.removeEventListener('focusin', closeWhenOutside);
    };
  }, [close, open]);

  const filteredOptions = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return options;
    return options.filter((option) =>
      option.toLocaleLowerCase().includes(normalizedQuery),
    );
  }, [options, query]);
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const summary =
    selected.length === 0 ? allLabel : selectedText(selected.length);

  const toggle = (option: string) => {
    onChange(
      selectedSet.has(option)
        ? selected.filter((value) => value !== option)
        : [...selected, option],
    );
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'Escape' || !open) return;
    event.preventDefault();
    event.stopPropagation();
    close(true);
  };

  return (
    <div className="grid gap-1" onKeyDown={handleKeyDown} ref={rootRef}>
      <span
        className="text-app-text-muted text-[length:var(--ui-text-caption)]"
        id={labelId}
      >
        {label}
      </span>
      <div className="relative">
        <button
          aria-controls={panelId}
          aria-expanded={open}
          aria-haspopup="true"
          aria-label={buttonLabel(summary)}
          className="flex min-w-[180px] items-center gap-2 rounded-[var(--ui-radius-md)] border border-app-border bg-app-surface px-2.5 py-1.5 text-left text-[length:var(--ui-text-body-sm)] text-app-text transition-colors hover:bg-app-surface-hover focus:outline-none focus:ring-2 focus:ring-app-accent/30"
          onClick={() => (open ? close() : setOpen(true))}
          ref={triggerRef}
          type="button"
        >
          <LayoutGrid
            aria-hidden="true"
            className="shrink-0 text-app-text-muted"
            size={15}
          />
          <span
            className={
              selected.length === 0
                ? 'min-w-0 flex-1 truncate text-app-text-muted'
                : 'min-w-0 flex-1 truncate'
            }
          >
            {summary}
          </span>
          <ChevronDown
            aria-hidden="true"
            className={`shrink-0 text-app-text-muted transition-transform ${
              open ? 'rotate-180' : ''
            }`}
            size={15}
          />
        </button>

        {open ? (
          <div
            aria-labelledby={labelId}
            className="absolute left-0 top-[calc(100%+4px)] z-[var(--ui-z-popover)] w-full min-w-[240px] rounded-[var(--ui-radius-md)] border border-app-border bg-app-surface shadow-lg"
            id={panelId}
            role="group"
          >
            <div className="border-b border-app-border p-2">
              <div className="flex items-center gap-1.5 rounded-[var(--ui-radius-sm)] border border-app-border bg-app-bg px-2 py-1">
                <Search
                  aria-hidden="true"
                  className="shrink-0 text-app-text-muted"
                  size={14}
                />
                <input
                  aria-label={searchLabel}
                  autoFocus
                  className="min-w-0 flex-1 bg-transparent text-[length:var(--ui-text-body-sm)] text-app-text outline-none"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={searchPlaceholder}
                  type="search"
                  value={query}
                />
              </div>
            </div>
            <div className="max-h-[240px] overflow-y-auto py-1">
              {filteredOptions.length === 0 ? (
                <div
                  className="px-3 py-2 text-[length:var(--ui-text-body-sm)] text-app-text-muted"
                  role="status"
                >
                  {noResultsLabel}
                </div>
              ) : (
                filteredOptions.map((option) => (
                  <label
                    className="flex w-full cursor-pointer items-center gap-2 px-3 py-1.5 text-[length:var(--ui-text-body-sm)] text-app-text hover:bg-app-surface-hover"
                    key={option}
                  >
                    <input
                      checked={selectedSet.has(option)}
                      className="shrink-0"
                      onChange={() => toggle(option)}
                      type="checkbox"
                    />
                    <span className="min-w-0 flex-1 truncate">{option}</span>
                  </label>
                ))
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
