export type PromptOptions = {
  title: string;
  description?: string;
  placeholder?: string;
  defaultValue?: string;
  submitLabel: string;
  cancelLabel: string;
};

export type PromptDialogRequest = PromptOptions & {
  resolve: (value: string | null) => void;
};

export type PromptDialogState = PromptDialogRequest | null;

type PromptDialogCompletion = {
  resolve: (value: string | null) => void;
  value: string | null;
};

type PromptDialogTransition = {
  state: PromptDialogState;
  completion: PromptDialogCompletion | null;
};

export function openPromptDialog(
  current: PromptDialogState,
  next: PromptDialogRequest,
): PromptDialogTransition {
  return {
    state: next,
    completion: current ? { resolve: current.resolve, value: null } : null,
  };
}

export function submitCurrentPromptDialog(
  current: PromptDialogState,
  value: string,
): PromptDialogTransition {
  return closePromptDialog(current, value);
}

export function cancelCurrentPromptDialog(
  current: PromptDialogState,
): PromptDialogTransition {
  return closePromptDialog(current, null);
}

function closePromptDialog(
  current: PromptDialogState,
  value: string | null,
): PromptDialogTransition {
  return {
    state: null,
    completion: current ? { resolve: current.resolve, value } : null,
  };
}
