import type { NavItem } from '@/src/app/shell/navigation-types';

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
  const scrollSelectedButtonIntoView = (
    highlighted: HTMLButtonElement | null,
  ) => {
    // scrollIntoView is unavailable in jsdom (test env).
    if (highlighted && typeof highlighted.scrollIntoView === 'function') {
      highlighted.scrollIntoView({ block: 'nearest' });
    }
  };

  // Menu is only mounted for non-empty candidate lists — the composer hides
  // the palette entirely when there are no matches so inputs like `/tmp` or
  // `/fmexx` fall through to a normal chat submission.
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="absolute bottom-full left-0 z-30 mb-2 w-full overflow-hidden rounded-xl border border-app-border bg-app-surface shadow-lg">
      <ul className="max-h-64 overflow-y-auto py-1">
        {items.map((item, index) => {
          const isActive = index === selectedIndex;
          return (
            <li key={item.id} data-menu-index={index}>
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
                ref={isActive ? scrollSelectedButtonIntoView : undefined}
                type="button"
              >
                <div className="flex size-7 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-accent">
                  <item.icon size={14} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="app-text-control-sm truncate text-app-ink">
                    {item.title}
                  </div>
                  {item.description ? (
                    <div className="app-text-micro truncate text-app-ink/55">
                      {item.description}
                    </div>
                  ) : null}
                </div>
                <span className="app-text-micro shrink-0 text-app-ink/55">
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
