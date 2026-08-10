export type ChatComposerKey =
  | 'ArrowDown'
  | 'ArrowUp'
  | 'Escape'
  | 'Enter'
  | string;

export type ChatComposerKeyIntent =
  | { type: 'none' }
  | { type: 'highlight-slash-index'; index: number }
  | { type: 'clear-slash-input' }
  | { type: 'select-slash-item'; index: number }
  | { type: 'submit-chat' };

export interface ChatComposerKeyState {
  input: string;
  isDisabled?: boolean;
  isSending: boolean;
  isSlashOpen: boolean;
  key: ChatComposerKey;
  selectedSlashIndex: number;
  shiftKey: boolean;
  slashItemCount: number;
}

export function isSlashCommandOpen(
  slashItems: { length: number } | null | undefined,
): boolean {
  return (
    slashItems !== null && slashItems !== undefined && slashItems.length > 0
  );
}

export function clampSelectedSlashIndex(
  slashIndex: number,
  slashItemCount: number,
): number {
  if (slashItemCount <= 0) {
    return 0;
  }
  return Math.min(Math.max(slashIndex, 0), slashItemCount - 1);
}

export function wrapSlashIndex(
  currentIndex: number,
  slashItemCount: number,
  direction: 'next' | 'previous',
): number {
  if (slashItemCount <= 0) {
    return 0;
  }
  const clampedIndex = clampSelectedSlashIndex(currentIndex, slashItemCount);
  if (direction === 'next') {
    return (clampedIndex + 1) % slashItemCount;
  }
  return clampedIndex <= 0 ? slashItemCount - 1 : clampedIndex - 1;
}

export function isChatSendDisabled({
  input,
  isDisabled,
  isSlashOpen,
}: {
  input: string;
  isDisabled?: boolean;
  isSlashOpen: boolean;
}): boolean {
  return !input.trim() || isSlashOpen || Boolean(isDisabled);
}

export function shouldSubmitChatForm({
  isSlashOpen,
}: {
  isSlashOpen: boolean;
}): boolean {
  return !isSlashOpen;
}

export function getChatComposerKeyIntent({
  input,
  isDisabled,
  isSending,
  isSlashOpen,
  key,
  selectedSlashIndex,
  shiftKey,
  slashItemCount,
}: ChatComposerKeyState): ChatComposerKeyIntent {
  if (isSlashOpen) {
    if (key === 'ArrowDown' && slashItemCount > 0) {
      return {
        type: 'highlight-slash-index',
        index: wrapSlashIndex(selectedSlashIndex, slashItemCount, 'next'),
      };
    }
    if (key === 'ArrowUp' && slashItemCount > 0) {
      return {
        type: 'highlight-slash-index',
        index: wrapSlashIndex(selectedSlashIndex, slashItemCount, 'previous'),
      };
    }
    if (key === 'Escape') {
      return { type: 'clear-slash-input' };
    }
    if (key === 'Enter' && !shiftKey && slashItemCount > 0) {
      return {
        type: 'select-slash-item',
        index: clampSelectedSlashIndex(selectedSlashIndex, slashItemCount),
      };
    }
    return { type: 'none' };
  }

  if (key !== 'Enter' || shiftKey || isSending) {
    return { type: 'none' };
  }
  if (
    isChatSendDisabled({
      input,
      isDisabled,
      isSlashOpen,
    })
  ) {
    return { type: 'none' };
  }
  return { type: 'submit-chat' };
}
