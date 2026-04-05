import { Badge } from '../primitives/badge';
import type { SidebarNavSection } from '../types';
import { cn } from '../utils/cn';

export interface SidebarNavProps {
  brand: { eyebrow: string; title: string };
  launcher?: { label: string; hint?: string; onSelect?: () => void };
  sections: SidebarNavSection[];
  footerBadges?: string[];
  className?: string;
}

export function SidebarNav({
  brand,
  launcher,
  sections,
  footerBadges,
  className,
}: SidebarNavProps) {
  return (
    <aside
      className={cn(
        'ui-scrollbar grid min-h-0 grid-rows-[auto_auto_1fr_auto] gap-3 overflow-y-auto border-r border-r-[var(--ui-color-border)] bg-[var(--ui-color-surface-sidebar)] p-4 text-white max-[980px]:overflow-visible max-[980px]:border-b max-[980px]:border-r-0',
        className,
      )}
    >
      <div className="grid gap-1 border-b border-b-white/12 px-2.5 pb-3 pt-1">
        <p className="m-0 text-xs font-semibold uppercase tracking-[0.08em] text-white/70">
          {brand.eyebrow}
        </p>
        <strong className="text-[1.08rem] tracking-[-0.01em]">{brand.title}</strong>
      </div>

      {launcher ? (
        <button
          type="button"
          onClick={launcher.onSelect}
          className="flex min-h-[34px] items-center justify-between rounded-[var(--ui-radius-md)] border border-white/14 bg-white/6 px-3 text-left text-sm font-medium text-white/90"
        >
          <span>{launcher.label}</span>
          {launcher.hint ? <span className="text-xs text-white/55">{launcher.hint}</span> : null}
        </button>
      ) : (
        <div />
      )}

      <nav aria-label="Primary" className="flex flex-col gap-3 self-start">
        {sections.map((section) => (
          <div key={section.id} className="grid content-start gap-1">
            <p className="m-0 px-2.5 text-[0.7rem] font-semibold uppercase tracking-[0.08em] text-white/55">
              {section.label}
            </p>
            {section.items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={item.onSelect}
                className={cn(
                  'flex min-h-[32px] items-center justify-between rounded-[var(--ui-radius-md)] px-2.5 text-left text-[0.93rem] text-white/86 transition-colors duration-[var(--ui-motion-fast)] hover:bg-white/6',
                  item.active ? 'bg-white/12 text-white' : '',
                )}
              >
                <span>{item.label}</span>
                {item.hint ? <span className="text-xs text-white/50">{item.hint}</span> : null}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="flex flex-wrap gap-1.5 px-2.5">
        {footerBadges?.map((badge) => (
          <Badge key={badge} tone="inverse">
            {badge}
          </Badge>
        ))}
      </div>
    </aside>
  );
}
