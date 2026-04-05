import type { ReactNode } from 'react';
import { useEffect } from 'react';

import { cn } from '../utils/cn';

interface MobileSidebarConfig {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label?: string;
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
  useEffect(() => {
    if (!mobileSidebar?.open) {
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
  }, [mobileSidebar?.open]);

  return (
    <div
      className={cn(
        'grid h-screen grid-cols-[264px_minmax(0,1fr)] bg-[var(--ui-color-bg)] max-[980px]:h-auto max-[980px]:grid-cols-1',
        className,
      )}
    >
      <div className="min-h-0 max-[980px]:hidden">{sidebar}</div>
      {mobileSidebar ? (
        <>
          <button
            aria-hidden={!mobileSidebar.open}
            className={cn(
              'fixed inset-0 z-40 bg-slate-950/45 transition-opacity duration-200 min-[981px]:hidden',
              mobileSidebar.open ? 'opacity-100' : 'pointer-events-none opacity-0',
            )}
            onClick={() => mobileSidebar.onOpenChange(false)}
            type="button"
          />
          <div
            className={cn(
              'fixed inset-y-0 left-0 z-50 h-dvh w-[min(86vw,320px)] overflow-hidden min-[981px]:hidden',
              mobileSidebar.open ? 'pointer-events-auto' : 'pointer-events-none',
            )}
          >
            <div
              className={cn(
                'relative h-full max-h-dvh transition-transform duration-200 ease-out',
                mobileSidebar.open ? 'translate-x-0' : '-translate-x-full',
              )}
            >
              <button
                className="absolute right-3 top-3 z-10 inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/12 bg-white/10 text-white"
                onClick={() => mobileSidebar.onOpenChange(false)}
                type="button"
              >
                <span aria-hidden="true">×</span>
                <span className="sr-only">메뉴 닫기</span>
              </button>
              <div className="h-full overflow-hidden shadow-[0_20px_60px_rgba(15,23,42,0.28)]">
                {sidebar}
              </div>
            </div>
          </div>
        </>
      ) : null}
      <main className="ui-scrollbar grid min-h-0 gap-5 overflow-y-auto p-6 max-[980px]:gap-4 max-[980px]:overflow-visible max-[980px]:p-4 max-[980px]:pt-0">
        {mobileSidebar ? (
          <div className="sticky top-0 z-30 -mx-4 hidden items-center justify-between border-b border-[var(--ui-color-border)] bg-[color:rgba(250,249,246,0.94)] px-4 py-3 backdrop-blur max-[980px]:flex">
            <div>
              <div className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                두원공조
              </div>
              <div className="text-base font-semibold text-[var(--ui-color-ink)]">
                아이두
              </div>
            </div>
            <button
              className="inline-flex items-center gap-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border-strong)] bg-[var(--ui-color-surface-raised)] px-3 py-2 text-sm font-semibold text-[var(--ui-color-ink)]"
              onClick={() => mobileSidebar.onOpenChange(true)}
              type="button"
            >
              <span aria-hidden="true">☰</span>
              <span>메뉴</span>
            </button>
          </div>
        ) : null}
        {header}
        {children}
      </main>
    </div>
  );
}
