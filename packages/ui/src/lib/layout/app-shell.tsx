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
        'grid h-screen grid-cols-[228px_minmax(0,1fr)] bg-ui-bg max-[980px]:h-auto max-[980px]:grid-cols-1',
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
                className="absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-[var(--ui-radius-sm)] border border-white/10 bg-white/6 text-white/90"
                onClick={() => mobileSidebar.onOpenChange(false)}
                type="button"
              >
                <span aria-hidden="true">×</span>
                <span className="sr-only">메뉴 닫기</span>
              </button>
              <div className="h-full overflow-hidden shadow-[var(--ui-shadow-lg)]">
                {sidebar}
              </div>
            </div>
          </div>
        </>
      ) : null}
      <main className="ui-scrollbar grid min-h-0 gap-0 overflow-y-auto px-4 pb-4 pt-0 max-[980px]:overflow-visible max-[980px]:px-4 max-[980px]:pb-4 max-[980px]:pt-0">
        {mobileSidebar ? (
          <div className="sticky top-0 z-30 -mx-4 hidden items-center justify-between border-b border-[var(--ui-color-border)] bg-ui-bg/94 px-4 py-2.5 backdrop-blur max-[980px]:flex">
            <div>
              <div className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[var(--ui-color-ink-subtle)]">
                두원공조
              </div>
              <div className="text-[0.98rem] font-semibold text-[var(--ui-color-ink)]">
                아이두
              </div>
            </div>
            <button
              className="inline-flex items-center gap-2 rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface px-2.5 py-1.5 text-sm font-semibold text-[var(--ui-color-ink)]"
              onClick={() => mobileSidebar.onOpenChange(true)}
              type="button"
            >
              <span aria-hidden="true">☰</span>
              <span>메뉴</span>
            </button>
          </div>
        ) : null}
        <div className="grid w-full max-w-[1500px] gap-2 pt-1.5 max-[980px]:gap-2 max-[980px]:pt-0">
          {header}
          {children}
        </div>
      </main>
    </div>
  );
}
