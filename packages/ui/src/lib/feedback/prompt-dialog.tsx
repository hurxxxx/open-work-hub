import { useCallback, useRef, useState } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';

import { PromptDialogContent } from './prompt-dialog-content';
import {
  cancelCurrentPromptDialog,
  openPromptDialog,
  submitCurrentPromptDialog,
  type PromptDialogState,
  type PromptOptions,
} from './prompt-dialog-state';

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export interface PromptDialogProps {
  open: boolean;
  title: string;
  description?: string;
  placeholder?: string;
  defaultValue?: string;
  submitLabel: string;
  cancelLabel: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

export function PromptDialog({
  open,
  title,
  description,
  placeholder,
  defaultValue = '',
  submitLabel,
  cancelLabel,
  onSubmit,
  onCancel,
}: PromptDialogProps) {
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) onCancel();
      }}
    >
      <DialogPrimitive.Portal>
        {open ? (
          <PromptDialogContent
            key={defaultValue}
            title={title}
            description={description}
            placeholder={placeholder}
            defaultValue={defaultValue}
            submitLabel={submitLabel}
            cancelLabel={cancelLabel}
            onSubmit={onSubmit}
            onCancel={onCancel}
          />
        ) : null}
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/* ------------------------------------------------------------------ */
/*  Hook – drop-in replacement for window.prompt                       */
/* ------------------------------------------------------------------ */

/**
 * Returns an async `prompt()` function and a `<PromptDialog />` element.
 * Render the element somewhere in your component tree.
 *
 * ```tsx
 * const { prompt, promptDialog } = usePrompt();
 * // …
 * const name = await prompt({ title: 'Rename', defaultValue: currentName });
 * if (!name) return;
 * // …
 * return <>{promptDialog}</>;
 * ```
 */
export function usePrompt() {
  const [state, setState] = useState<PromptDialogState>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const prompt = useCallback((options: PromptOptions) => {
    return new Promise<string | null>((resolve) => {
      const transition = openPromptDialog(stateRef.current, {
        ...options,
        resolve,
      });
      transition.completion?.resolve(transition.completion.value);
      stateRef.current = transition.state;
      setState(transition.state);
    });
  }, []);

  const handleSubmit = useCallback(
    (value: string) => {
      const transition = submitCurrentPromptDialog(state, value);
      transition.completion?.resolve(transition.completion.value);
      stateRef.current = transition.state;
      setState(transition.state);
    },
    [state],
  );

  const handleCancel = useCallback(() => {
    const transition = cancelCurrentPromptDialog(state);
    transition.completion?.resolve(transition.completion.value);
    stateRef.current = transition.state;
    setState(transition.state);
  }, [state]);

  const promptDialog = state ? (
    <PromptDialog
      open
      title={state.title}
      description={state.description}
      placeholder={state.placeholder}
      defaultValue={state.defaultValue}
      submitLabel={state.submitLabel}
      cancelLabel={state.cancelLabel}
      onSubmit={handleSubmit}
      onCancel={handleCancel}
    />
  ) : null;

  return { prompt, promptDialog };
}
