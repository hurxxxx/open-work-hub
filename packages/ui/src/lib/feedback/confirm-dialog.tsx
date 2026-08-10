import { useCallback, useRef, useState } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';

import { Button } from '../primitives/button';
import { cn } from '../utils/cn';
import {
  cancelCurrentDialog,
  confirmCurrentDialog,
  openConfirmDialog,
  type ConfirmDialogState,
  type ConfirmDialogTransition,
  type ConfirmDialogVariant,
  type ConfirmOptions,
} from './confirm-dialog-state';

export type { ConfirmOptions } from './confirm-dialog-state';

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  /** "danger" renders the confirm button in red. */
  variant?: ConfirmDialogVariant;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  variant = 'default',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) onCancel();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[calc(var(--ui-z-drawer)-1)] bg-ui-static-black/32 backdrop-blur-sm" />
        <DialogPrimitive.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-[var(--ui-z-drawer)] w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2',
            'flex flex-col rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-ui-surface-raised shadow-[var(--ui-shadow-lg)] outline-none',
          )}
        >
          <div className="px-5 pt-5 pb-3">
            <DialogPrimitive.Title className="m-0 text-[length:var(--ui-text-h3)] font-semibold tracking-[-0.02em] text-[var(--ui-color-ink)]">
              {title}
            </DialogPrimitive.Title>
            <DialogPrimitive.Description className="mt-2 text-[length:var(--ui-text-body-sm)] leading-relaxed text-[var(--ui-color-ink-muted)]">
              {description}
            </DialogPrimitive.Description>
          </div>

          <div className="flex items-center justify-end gap-2 px-5 py-4">
            <Button variant="ghost" onClick={onCancel}>
              {cancelLabel}
            </Button>
            <Button
              variant="primary"
              className={
                variant === 'danger'
                  ? 'border-ui-danger bg-ui-danger hover:bg-ui-danger/90'
                  : undefined
              }
              onClick={onConfirm}
            >
              {confirmLabel}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/* ------------------------------------------------------------------ */
/*  Hook – drop-in replacement for window.confirm                      */
/* ------------------------------------------------------------------ */

/**
 * Returns an async `confirm()` function and a `<ConfirmDialog />` element.
 * Render the element somewhere in your component tree.
 *
 * ```tsx
 * const { confirm, confirmDialog } = useConfirm();
 * // …
 * if (!await confirm({ description: 'Delete this item?' })) return;
 * // …
 * return <>{confirmDialog}</>;
 * ```
 */
export function useConfirm() {
  const [state, setState] = useState<ConfirmDialogState>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const applyTransition = useCallback((transition: ConfirmDialogTransition) => {
    stateRef.current = transition.state;
    transition.completion?.resolve(transition.completion.value);
    setState(transition.state);
  }, []);

  const confirm = useCallback(
    (options: ConfirmOptions) => {
      return new Promise<boolean>((resolve) => {
        applyTransition(
          openConfirmDialog(stateRef.current, { ...options, resolve }),
        );
      });
    },
    [applyTransition],
  );

  const handleConfirm = useCallback(() => {
    applyTransition(confirmCurrentDialog(stateRef.current));
  }, [applyTransition]);

  const handleCancel = useCallback(() => {
    applyTransition(cancelCurrentDialog(stateRef.current));
  }, [applyTransition]);

  const confirmDialog = state ? (
    <ConfirmDialog
      open
      title={state.title}
      description={state.description}
      confirmLabel={state.confirmLabel}
      cancelLabel={state.cancelLabel}
      variant={state.variant}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  ) : null;

  return { confirm, confirmDialog };
}
