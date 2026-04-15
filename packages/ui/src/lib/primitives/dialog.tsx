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
  /** Maximum width class, e.g. "max-w-lg" or "max-w-3xl". Defaults to "max-w-lg". Ignored when ``fullSize`` is true. */
  maxWidth?: string;
  /**
   * When true, the dialog occupies a near-fullscreen fixed size
   * (~96vw × ~92vh) regardless of content. Use for dense data tables or
   * multi-pane experiences where you want a predictable, large canvas
   * rather than a dialog that shrinks to its children.
   */
  fullSize?: boolean;
  /**
   * When true, the dialog renders **without** the built-in header / padding /
   * scroll wrapper / actions footer. The ``children`` element fills the entire
   * dialog surface and is responsible for its own layout (header, scroll,
   * close button). ``title`` and ``description`` are still rendered for
   * accessibility but visually hidden.
   *
   * Use this when embedding a self-contained component that already manages
   * its own chrome (e.g. ``MeetingDetail``) inside a modal context.
   */
  embedded?: boolean;
  /**
   * Whether interacting outside the dialog (pointer-down outside or focus
   * outside) should close it. Defaults to ``true``. Set to ``false`` for
   * form-heavy modals where an accidental misclick — for example, on a
   * native datetime picker that overflows the dialog — would otherwise
   * destroy the user's in-progress edits. ESC and the close button still
   * work in either mode.
   */
  dismissOnInteractOutside?: boolean;
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  actions,
  maxWidth = 'max-w-lg',
  fullSize = false,
  embedded = false,
  dismissOnInteractOutside = true,
}: DialogProps) {
  const blockOutside = dismissOnInteractOutside
    ? undefined
    : (event: Event) => event.preventDefault();
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[calc(var(--ui-z-drawer)-1)] bg-slate-950/32 backdrop-blur-sm" />
        <DialogPrimitive.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[var(--ui-z-drawer)] -translate-x-1/2 -translate-y-1/2',
            'flex flex-col rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-ui-surface-raised shadow-[var(--ui-shadow-lg)] outline-none overflow-hidden',
            fullSize
              ? 'h-[92vh] w-[96vw] max-w-[1600px]'
              : ['w-[calc(100vw-2rem)] max-h-[85vh]', maxWidth],
          )}
          onPointerDownOutside={blockOutside}
          onInteractOutside={blockOutside}
        >
          {embedded ? (
            <>
              {/* Accessibility: still expose title/description to screen readers
                  even though the visual header is suppressed. */}
              <DialogPrimitive.Title className="sr-only">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="sr-only">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
              <div className="flex min-h-0 flex-1 flex-col">{children}</div>
            </>
          ) : (
            <>
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
            </>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
