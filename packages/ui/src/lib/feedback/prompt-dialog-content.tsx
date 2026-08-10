import { useCallback, useEffect, useRef, useState } from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';

import { Button } from '../primitives/button';
import { Input } from '../primitives/input';
import { cn } from '../utils/cn';

interface PromptDialogContentProps {
  title: string;
  description?: string;
  placeholder?: string;
  defaultValue: string;
  submitLabel: string;
  cancelLabel: string;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}

export function PromptDialogContent({
  title,
  description,
  placeholder,
  defaultValue,
  submitLabel,
  cancelLabel,
  onSubmit,
  onCancel,
}: PromptDialogContentProps) {
  const [value, setValue] = useState(defaultValue);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const frame = requestAnimationFrame(() => inputRef.current?.select());
    return () => cancelAnimationFrame(frame);
  }, []);

  const handleSubmit = useCallback(() => {
    const nextValue = value.trim();
    if (nextValue) {
      onSubmit(nextValue);
    }
  }, [onSubmit, value]);

  return (
    <>
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
          {description ? (
            <DialogPrimitive.Description className="mt-2 text-[length:var(--ui-text-body-sm)] leading-relaxed text-[var(--ui-color-ink-muted)]">
              {description}
            </DialogPrimitive.Description>
          ) : null}
        </div>

        <div className="px-5 pb-2">
          <Input
            ref={inputRef}
            value={value}
            placeholder={placeholder}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSubmit();
            }}
          />
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-4">
          <Button variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={!value.trim()}
          >
            {submitLabel}
          </Button>
        </div>
      </DialogPrimitive.Content>
    </>
  );
}
