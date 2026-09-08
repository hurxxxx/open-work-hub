import type { LucideProps } from 'lucide-react';
import type { ComponentType } from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@/src/lib/utils';

type AppBarRailControlTone = 'default' | 'fixed';

export function appBarRailControlClassName(
  active: boolean,
  className?: string,
  tone: AppBarRailControlTone = 'default',
) {
  const inactiveClassName =
    tone === 'fixed'
      ? 'border-transparent bg-transparent text-sky-100/85 hover:bg-white/10 hover:text-white'
      : 'border-white/10 bg-white/10 text-gray-300 hover:border-white/20 hover:bg-white/15 hover:text-white';

  return cn(
    'group relative inline-flex shrink-0 items-center justify-center border transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent/40',
    tone === 'fixed' ? 'size-10 rounded-lg' : 'size-11 rounded-xl',
    active
      ? tone === 'fixed'
        ? 'border-transparent bg-white/12 text-white shadow-none'
        : 'border-white bg-white text-slate-950 shadow-inner'
      : inactiveClassName,
    className,
  );
}

export function AppBarRailTooltip({ title }: { title: string }) {
  return (
    <div className="app-text-micro pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 whitespace-nowrap rounded bg-gray-950 px-2 py-1 text-white opacity-0 group-hover:opacity-100">
      {title}
    </div>
  );
}

export function AppBarRailActiveIndicator() {
  return (
    <div className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-orange-400 shadow-[0_0_0_1px_rgba(15,23,42,0.18)]" />
  );
}

export function AppBarIconLink({
  active,
  icon: Icon,
  tone = 'default',
  title,
  to,
}: {
  active: boolean;
  icon: ComponentType<LucideProps>;
  tone?: AppBarRailControlTone;
  title: string;
  to: string;
}) {
  return (
    <Link
      aria-label={title}
      className={appBarRailControlClassName(active, undefined, tone)}
      title={title}
      to={to}
    >
      <Icon aria-hidden size={22} strokeWidth={2.25} />
      <AppBarRailTooltip title={title} />
      {active ? <AppBarRailActiveIndicator /> : null}
    </Link>
  );
}
