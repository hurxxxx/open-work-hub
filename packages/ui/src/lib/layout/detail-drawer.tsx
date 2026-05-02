import * as Dialog from '@radix-ui/react-dialog';

import type { DetailDrawerProps } from '../types';
import { Button } from '../primitives/button';
import { cn } from '../utils/cn';

export function DetailDrawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  actions,
  closeLabel = 'Close details',
  contentClassName,
  embedded = false,
  side = 'right',
}: DetailDrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[calc(var(--ui-z-drawer)-1)] bg-slate-950/32" />
        <Dialog.Content
          className={cn(
            'fixed top-0 z-[var(--ui-z-drawer)] flex h-screen w-[min(420px,100vw)] flex-col bg-ui-surface-raised shadow-[var(--ui-shadow-lg)] outline-none',
            side === 'left'
              ? 'left-0 border-r border-r-[var(--ui-color-border)]'
              : 'right-0 border-l border-l-[var(--ui-color-border)]',
            embedded ? 'overflow-hidden' : 'gap-3 p-4',
            contentClassName,
          )}
        >
          {embedded ? (
            <>
              <Dialog.Title className="sr-only">
                {title}
              </Dialog.Title>
              {description ? (
                <Dialog.Description className="sr-only">
                  {description}
                </Dialog.Description>
              ) : null}
              <div className="min-h-0 flex-1">{children}</div>
            </>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3 border-b border-b-[var(--ui-color-border)] pb-3">
                <div className="grid gap-1">
                  <Dialog.Title className="m-0 text-[1rem] font-semibold tracking-[-0.02em] text-[var(--ui-color-ink)]">
                    {title}
                  </Dialog.Title>
                  {description ? (
                    <Dialog.Description className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">
                      {description}
                    </Dialog.Description>
                  ) : null}
                </div>
                <Dialog.Close asChild>
                  <Button aria-label={closeLabel} variant="ghost" size="icon">
                    <span aria-hidden="true">×</span>
                  </Button>
                </Dialog.Close>
              </div>

              <div className="ui-scrollbar min-h-0 flex-1 overflow-y-auto">{children}</div>

              {actions ? <div className="flex flex-col gap-2">{actions}</div> : null}
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
