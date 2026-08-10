import type { ReactNode } from 'react';
import { useEffect } from 'react';

import { cn } from '../utils/cn';

interface MobileSidebarConfig {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label?: string;
  closeLabel?: string;
  brandEyebrow?: string;
  brandTitle?: string;
}

export interface AppShellProps {
  sidebar: ReactNode;
  header?: ReactNode;
  children: ReactNode;
  className?: string;
  mobileSidebar?: MobileSidebarConfig;
}

export function AppShell({
  sidebar,
  header,
  children,
  className,
  mobileSidebar,
}: AppShellProps) {
  useBodyScrollLock(mobileSidebar?.open ?? false);

  return (
    <div
      className={cn(
        'grid h-screen grid-cols-[228px_minmax(0,1fr)] bg-ui-bg max-[980px]:h-auto max-[980px]:grid-cols-1',
        className,
      )}
    >
      <div className="min-h-0 max-[980px]:hidden">{sidebar}</div>
      {mobileSidebar ? (
        <MobileSidebarSheet config={mobileSidebar} sidebar={sidebar} />
      ) : null}
      <main className="ui-scrollbar grid min-h-0 gap-0 overflow-y-auto px-4 pb-4 pt-0 max-[980px]:overflow-visible max-[980px]:px-4 max-[980px]:pb-4 max-[980px]:pt-0">
        {mobileSidebar ? <MobileSidebarHeader config={mobileSidebar} /> : null}
        <div className="grid w-full max-w-[1500px] gap-2 pt-1.5 max-[980px]:gap-2 max-[980px]:pt-0">
          {header}
          {children}
        </div>
      </main>
    </div>
  );
}

function useBodyScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) {
      return;
    }

    const previousBodyOverflow = document.body.style.overflow;
    const previousDocumentOverflow = document.documentElement.style.overflow;

    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overflow = previousDocumentOverflow;
    };
  }, [locked]);
}

function MobileSidebarSheet({
  config,
  sidebar,
}: {
  config: MobileSidebarConfig;
  sidebar: ReactNode;
}) {
  return (
    <>
      <button
        aria-label={config.closeLabel ?? 'Close sidebar'}
        className={cn(
          'fixed inset-0 z-40 bg-ui-static-black/45 transition-opacity duration-200 min-[981px]:hidden',
          config.open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={() => config.onOpenChange(false)}
        tabIndex={config.open ? 0 : -1}
        type="button"
      />
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 h-dvh w-[min(86vw,320px)] overflow-hidden min-[981px]:hidden',
          config.open ? 'pointer-events-auto' : 'pointer-events-none',
        )}
      >
        <div
          className={cn(
            'relative h-full max-h-dvh transition-transform duration-200 ease-out',
            config.open ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <button
            className="absolute right-3 top-3 z-10 inline-flex size-8 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/10 bg-white/6 text-white/90"
            onClick={() => config.onOpenChange(false)}
            type="button"
          >
            <span aria-hidden="true">×</span>
            {config.closeLabel ? (
              <span className="sr-only">{config.closeLabel}</span>
            ) : null}
          </button>
          <div className="h-full overflow-hidden shadow-[var(--ui-shadow-lg)]">
            {sidebar}
          </div>
        </div>
      </div>
    </>
  );
}

function MobileSidebarHeader({ config }: { config: MobileSidebarConfig }) {
  return (
    <div className="sticky top-0 z-30 -mx-4 hidden items-center justify-between border-b border-[var(--ui-color-border)] bg-ui-bg/94 px-4 py-2.5 backdrop-blur max-[980px]:flex">
      <div>
        {config.brandEyebrow ? (
          <div className="text-[length:var(--ui-text-overline)] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
            {config.brandEyebrow}
          </div>
        ) : null}
        {config.brandTitle ? (
          <div className="text-[length:var(--ui-text-h3)] font-semibold text-[var(--ui-color-ink)]">
            {config.brandTitle}
          </div>
        ) : null}
      </div>
      <button
        className="ui-primitive-control-body-sm inline-flex items-center gap-2 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface px-2.5 py-1.5 text-[length:var(--ui-text-body-sm)] font-semibold text-[var(--ui-color-ink)]"
        onClick={() => config.onOpenChange(true)}
        type="button"
      >
        <span aria-hidden="true">☰</span>
        {config.label ? <span>{config.label}</span> : null}
      </button>
    </div>
  );
}
