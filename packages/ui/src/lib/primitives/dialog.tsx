import * as DialogPrimitive from '@radix-ui/react-dialog';
import type { ReactNode } from 'react';

import { Button } from './button';
import { cn } from '../utils/cn';

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
  /** Maximum width class, e.g. "max-w-lg" or "max-w-3xl". Defaults to "max-w-lg". */
  maxWidth?: string;
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  actions,
  maxWidth = 'max-w-lg',
}: DialogProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[calc(var(--ui-z-drawer)-1)] bg-slate-950/32 backdrop-blur-sm" />
        <DialogPrimitive.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[var(--ui-z-drawer)] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2',
            'flex max-h-[85vh] flex-col rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface-raised)] shadow-[var(--ui-shadow-lg)] outline-none',
            maxWidth,
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-b-[var(--ui-color-border)] px-5 py-4">
            <div className="grid gap-1">
              <DialogPrimitive.Title className="m-0 text-[1rem] font-semibold tracking-[-0.02em] text-[var(--ui-color-ink)]">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="m-0 text-[0.84rem] text-[var(--ui-color-ink-muted)]">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            <DialogPrimitive.Close asChild>
              <Button aria-label="Close dialog" variant="ghost" size="icon">
                <span aria-hidden="true">×</span>
              </Button>
            </DialogPrimitive.Close>
          </div>

          <div className="ui-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {children}
          </div>

          {actions ? (
            <div className="flex items-center justify-end gap-2 border-t border-t-[var(--ui-color-border)] px-5 py-3">
              {actions}
            </div>
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
