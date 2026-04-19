import { useEffect, useMemo, useRef } from 'react';

import type { NavItem } from '@/src/constants';

export interface SlashCommandMenuProps {
  items: NavItem[];
  selectedIndex: number;
  onSelect: (item: NavItem) => void;
  onHighlight: (index: number) => void;
}

export function SlashCommandMenu({
  items,
  selectedIndex,
  onSelect,
  onHighlight,
}: SlashCommandMenuProps) {
  const listRef = useRef<HTMLUListElement | null>(null);

  useEffect(() => {
    const list = listRef.current;
    if (!list) {
      return;
    }
    const highlighted = list.querySelector<HTMLLIElement>(
      `[data-menu-index="${selectedIndex}"]`,
    );
    // scrollIntoView is unavailable in jsdom (test env).
    if (highlighted && typeof highlighted.scrollIntoView === 'function') {
      highlighted.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  // Menu is only mounted for non-empty candidate lists — the composer hides
  // the palette entirely when there are no matches so inputs like `/tmp` or
  // `/fmexx` fall through to a normal chat submission.
  if (items.length === 0) {
    return null;
  }

  return (
    <div
      className="absolute bottom-full left-0 z-30 mb-2 w-full overflow-hidden rounded-xl border border-app-border bg-app-surface shadow-lg"
      role="listbox"
    >
      <ul
        ref={listRef}
        className="max-h-64 overflow-y-auto py-1"
      >
        {items.map((item, index) => {
          const isActive = index === selectedIndex;
          return (
            <li
              key={item.id}
              data-menu-index={index}
              role="option"
              aria-selected={isActive}
            >
              <button
                className={`flex w-full items-center gap-3 px-3 py-2 text-left transition-colors ${
                  isActive
                    ? 'bg-app-bg text-app-ink'
                    : 'text-app-ink hover:bg-app-bg'
                }`}
                onClick={() => onSelect(item)}
                onMouseEnter={() => onHighlight(index)}
                // Prevent textarea blur so Enter keeps working after mouse hover.
                onMouseDown={(event) => event.preventDefault()}
                type="button"
              >
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                  <item.icon size={14} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="app-text-control-sm truncate text-app-ink">
                    {item.title}
                  </div>
                  {item.description ? (
                    <div className="app-text-micro truncate text-gray-500">
                      {item.description}
                    </div>
                  ) : null}
                </div>
                <span className="app-text-micro shrink-0 text-gray-500">
                  {item.category}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// A buffer qualifies as a slash command only when it's a single "/" followed
// by identifier-safe characters — no additional "/" (so filesystem paths and
// URLs like `/api/v1/users` remain plain prompts) and no whitespace (so
// sentences like "/how do I" fall through). Empty "/" alone also opens the
// menu so users can browse the full list.
const SLASH_COMMAND_PATTERN = /^\/[^/\s]*$/;

export function isSlashCommandBuffer(input: string): boolean {
  return SLASH_COMMAND_PATTERN.test(input);
}

export function useSlashCommandItems(source: NavItem[], rawInput: string) {
  return useMemo(() => {
    if (!isSlashCommandBuffer(rawInput)) {
      return null;
    }
    const query = rawInput.slice(1).trim().toLowerCase();
    const aiItems = source.filter((item) => item.appId === 'ai');
    if (!query) {
      return aiItems;
    }
    return aiItems.filter((item) => {
      const haystack = `${item.title} ${item.description ?? ''} ${item.id}`.toLowerCase();
      return haystack.includes(query);
    });
  }, [source, rawInput]);
}
