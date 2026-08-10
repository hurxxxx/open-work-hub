import type { ReactNode } from 'react';
import { Button, Dialog } from '@open-work-hub/ui';

export const FORM_FIELD_CONTROL_CLASS_NAME =
  'app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none';

export const FORM_TEXTAREA_CONTROL_CLASS_NAME = `${FORM_FIELD_CONTROL_CLASS_NAME} resize-none`;

export type FormDialogProps = {
  cancelLabel: ReactNode;
  children: ReactNode;
  closeLabel: string;
  description?: ReactNode;
  dismissOnInteractOutside?: boolean;
  maxWidth?: string;
  onCancel: () => void;
  onPrimary: () => void;
  open: boolean;
  primaryDisabled?: boolean;
  primaryLabel: ReactNode;
  primaryPendingLabel?: ReactNode;
  submitting?: boolean;
  title: ReactNode;
};

export function FormDialog({
  cancelLabel,
  children,
  closeLabel,
  description,
  dismissOnInteractOutside,
  maxWidth = 'max-w-lg',
  onCancel,
  onPrimary,
  open,
  primaryDisabled = false,
  primaryLabel,
  primaryPendingLabel,
  submitting = false,
  title,
}: FormDialogProps) {
  return (
    <Dialog
      closeLabel={closeLabel}
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onCancel();
      }}
      title={title}
      description={description}
      maxWidth={maxWidth}
      dismissOnInteractOutside={dismissOnInteractOutside}
      actions={
        <FormDialogActions
          cancelLabel={cancelLabel}
          onCancel={onCancel}
          onPrimary={onPrimary}
          primaryDisabled={primaryDisabled}
          primaryLabel={primaryLabel}
          primaryPendingLabel={primaryPendingLabel}
          submitting={submitting}
        />
      }
    >
      {children}
    </Dialog>
  );
}

export type FormDialogActionsProps = {
  cancelLabel: ReactNode;
  onCancel: () => void;
  onPrimary: () => void;
  primaryDisabled?: boolean;
  primaryLabel: ReactNode;
  primaryPendingLabel?: ReactNode;
  submitting?: boolean;
};

export function FormDialogActions({
  cancelLabel,
  onCancel,
  onPrimary,
  primaryDisabled = false,
  primaryLabel,
  primaryPendingLabel,
  submitting = false,
}: FormDialogActionsProps) {
  return (
    <div className="flex w-full items-center justify-end gap-3">
      <Button variant="secondary" onClick={onCancel}>
        {cancelLabel}
      </Button>
      <Button
        variant="primary"
        onClick={onPrimary}
        disabled={primaryDisabled || submitting}
      >
        {submitting && primaryPendingLabel ? primaryPendingLabel : primaryLabel}
      </Button>
    </div>
  );
}

export type FormFieldRowProps = {
  children: ReactNode;
  htmlFor?: string;
  label: ReactNode;
  optionalLabel?: ReactNode;
  required?: boolean;
};

export function FormFieldRow({
  children,
  htmlFor,
  label,
  optionalLabel,
  required = false,
}: FormFieldRowProps) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="app-text-control-sm text-app-ink/70">
        {label}
        {required ? (
          <>
            {' '}
            <span className="text-[var(--ui-color-danger)]">*</span>
          </>
        ) : null}
        {optionalLabel ? (
          <>
            {' '}
            <span className="text-app-ink/30">({optionalLabel})</span>
          </>
        ) : null}
      </label>
      {children}
    </div>
  );
}
