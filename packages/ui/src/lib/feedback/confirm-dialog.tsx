import { useCallback, useRef, useState, type RefObject } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';

import { Button } from '../primitives/button';
import { cn } from '../utils/cn';
import {
  dialogContentLayerClass,
  dialogOverlayLayerClass,
} from '../overlay/dialog-surface-model';
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
  /** Element that should regain focus after the dialog closes. */
  returnFocusRef?: RefObject<HTMLElement | null>;
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
  returnFocusRef,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const fallbackReturnFocusRef = useRef<HTMLElement | null>(null);
  const handleOpenAutoFocus = () => {
    const activeElement = document.activeElement;
    fallbackReturnFocusRef.current =
      activeElement instanceof HTMLElement ? activeElement : null;
  };
  const handleCloseAutoFocus = (event: Event) => {
    const target = returnFocusRef?.current ?? fallbackReturnFocusRef.current;
    fallbackReturnFocusRef.current = null;
    if (!target?.isConnected) return;
    event.preventDefault();
    target.focus();
  };

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) onCancel();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 bg-ui-static-black/32 backdrop-blur-sm',
            dialogOverlayLayerClass('elevated'),
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed left-1/2 top-1/2 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2',
            dialogContentLayerClass('elevated'),
            'flex flex-col rounded-[var(--ui-radius-lg)] border border-[var(--ui-color-border)] bg-ui-surface-raised shadow-[var(--ui-shadow-lg)] outline-none',
          )}
          onCloseAutoFocus={handleCloseAutoFocus}
          onOpenAutoFocus={handleOpenAutoFocus}
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
                  ? 'border-ui-danger-border bg-ui-danger-bg text-ui-danger-text hover:bg-ui-danger-border'
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
  const returnFocusRef = useRef<HTMLElement | null>(null);
  stateRef.current = state;

  const applyTransition = useCallback((transition: ConfirmDialogTransition) => {
    stateRef.current = transition.state;
    transition.completion?.resolve(transition.completion.value);
    setState(transition.state);
  }, []);

  const confirm = useCallback(
    (options: ConfirmOptions) => {
      // A caller can disable its action while awaiting confirmation. Capture
      // before that render blurs the button, rather than when the portal mounts.
      const activeElement = document.activeElement;
      returnFocusRef.current =
        activeElement instanceof HTMLElement ? activeElement : null;
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
      returnFocusRef={returnFocusRef}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
    />
  ) : null;

  return { confirm, confirmDialog };
}
