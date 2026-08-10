export type ToastTone = 'info' | 'success' | 'error';

export type ToastRecord = {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
};

export function toastToneClass(tone: ToastTone): string {
  switch (tone) {
    case 'success':
      return 'border-transparent bg-[color-mix(in_oklab,var(--ui-color-success)_12%,white)] text-[var(--ui-color-success)]';
    case 'error':
      return 'border-transparent bg-[color-mix(in_oklab,var(--ui-color-danger)_14%,white)] text-[var(--ui-color-danger)]';
    default:
      return 'border-[var(--ui-color-border)] bg-ui-surface-raised text-[var(--ui-color-ink)]';
  }
}

export function createToastRecord({
  description,
  id,
  title,
  tone,
}: {
  description?: string;
  id: string;
  title: string;
  tone: ToastTone;
}): ToastRecord {
  return {
    id,
    title,
    description,
    tone,
  };
}

export function appendToastRecord(
  current: readonly ToastRecord[],
  toast: ToastRecord,
): ToastRecord[] {
  return [...current, toast];
}

export function dismissToastRecord(
  current: readonly ToastRecord[],
  toastId: string,
): ToastRecord[] {
  return current.filter((item) => item.id !== toastId);
}
