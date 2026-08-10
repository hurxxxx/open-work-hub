import { Badge } from '../primitives/badge';
import type { SidebarNavSection } from '../types';
import { cn } from '../utils/cn';

export interface SidebarNavProps {
  brand: { eyebrow: string; title: string };
  launcher?: { label: string; hint?: string; onSelect?: () => void };
  sections: SidebarNavSection[];
  ariaLabel?: string;
  footerBadges?: string[];
  className?: string;
}

export function SidebarNav({
  brand,
  launcher,
  sections,
  ariaLabel,
  footerBadges,
  className,
}: SidebarNavProps) {
  return (
    <aside
      className={cn(
        'ui-scrollbar grid h-full min-h-0 grid-rows-[auto_auto_1fr_auto] gap-2 overflow-y-auto border-r border-r-white/6 bg-ui-surface-sidebar p-2.5 text-white max-[980px]:border-b max-[980px]:border-r-0',
        className,
      )}
    >
      <div className="grid gap-1 border-b border-b-white/10 px-1.5 pb-2 pt-1">
        <p className="m-0 text-[length:var(--ui-text-overline)] font-semibold uppercase tracking-[0.08em] text-white/56">
          {brand.eyebrow}
        </p>
        <strong className="text-[length:var(--ui-text-h3)] tracking-[-0.01em] text-white">{brand.title}</strong>
      </div>

      {launcher ? (
        <button
          type="button"
          onClick={launcher.onSelect}
          className="ui-primitive-control-body flex min-h-[32px] items-center justify-between rounded-[var(--ui-radius-sm)] border border-white/10 bg-white/5 px-2.5 text-left text-[length:var(--ui-text-body)] font-medium text-white/88"
        >
          <span>{launcher.label}</span>
          {launcher.hint ? <span className="text-[length:var(--ui-text-caption)] text-white/48">{launcher.hint}</span> : null}
        </button>
      ) : (
        <div />
      )}

      <nav aria-label={ariaLabel} className="flex flex-col gap-2.5 self-start">
        {sections.map((section) => (
          <div key={section.id} className="grid content-start gap-1">
            <p className="m-0 px-2 text-[length:var(--ui-text-overline)] font-semibold uppercase tracking-[0.08em] text-white/42">
              {section.label}
            </p>
            {section.items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={item.onSelect}
                className={cn(
                  'ui-primitive-control-body-normal flex min-h-[30px] items-center justify-between rounded-[var(--ui-radius-sm)] px-2 text-left text-[length:var(--ui-text-body)] text-white/76 transition-colors duration-[var(--ui-motion-fast)] hover:bg-white/7 hover:text-white',
                  item.active ? 'bg-white/10 text-white' : '',
                )}
              >
                <span>{item.label}</span>
                {item.hint ? <span className="text-[length:var(--ui-text-caption)] text-white/38">{item.hint}</span> : null}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="flex flex-wrap gap-1 px-2">
        {footerBadges?.map((badge) => (
          <Badge key={badge} tone="inverse">
            {badge}
          </Badge>
        ))}
      </div>
    </aside>
  );
}
