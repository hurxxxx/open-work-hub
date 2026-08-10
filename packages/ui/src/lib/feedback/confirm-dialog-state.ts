export type ConfirmDialogVariant = 'default' | 'danger';

export type ConfirmOptions = {
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  variant?: ConfirmDialogVariant;
};

export type ConfirmDialogRequest = ConfirmOptions & {
  resolve: (value: boolean) => void;
};

export type ConfirmDialogState = ConfirmDialogRequest | null;

type ConfirmDialogCompletion = {
  resolve: (value: boolean) => void;
  value: boolean;
};

export type ConfirmDialogTransition = {
  state: ConfirmDialogState;
  completion: ConfirmDialogCompletion | null;
};

export function openConfirmDialog(
  current: ConfirmDialogState,
  next: ConfirmDialogRequest,
): ConfirmDialogTransition {
  return {
    state: next,
    completion: current ? { resolve: current.resolve, value: false } : null,
  };
}

export function confirmCurrentDialog(
  current: ConfirmDialogState,
): ConfirmDialogTransition {
  return closeConfirmDialog(current, true);
}

export function cancelCurrentDialog(
  current: ConfirmDialogState,
): ConfirmDialogTransition {
  return closeConfirmDialog(current, false);
}

function closeConfirmDialog(
  current: ConfirmDialogState,
  value: boolean,
): ConfirmDialogTransition {
  return {
    state: null,
    completion: current ? { resolve: current.resolve, value } : null,
  };
}
