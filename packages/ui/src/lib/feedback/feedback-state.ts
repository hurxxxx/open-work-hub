export const FEEDBACK_DURATION_MS = 6000;
export const FEEDBACK_PENDING_LIMIT = 20;
export const FEEDBACK_VISIBLE_LIMIT = 3;

export type FeedbackTone = 'info' | 'success' | 'warning' | 'error';
export type FeedbackAnnouncement = 'polite' | 'assertive';

export interface FeedbackAction {
  label: string;
  altText: string;
  onAction: () => void;
}

export interface FeedbackInput {
  title: string;
  description?: string;
  tone: FeedbackTone;
  announcement?: FeedbackAnnouncement;
  dedupeKey?: string;
  action?: FeedbackAction;
}

export interface FeedbackRecord extends FeedbackInput {
  id: string;
  announcement: FeedbackAnnouncement;
}

export interface FeedbackQueue {
  visible: FeedbackRecord[];
  pending: FeedbackRecord[];
}

export const EMPTY_FEEDBACK_QUEUE: FeedbackQueue = {
  visible: [],
  pending: [],
};

export function feedbackToneClass(tone: FeedbackTone): string {
  switch (tone) {
    case 'success':
      return 'border-l-[3px] border-l-[var(--ui-color-success)]';
    case 'warning':
      return 'border-l-[3px] border-l-[var(--ui-color-warning)]';
    case 'error':
      return 'border-l-[3px] border-l-[var(--ui-color-danger)]';
    default:
      return 'border-l-[3px] border-l-[var(--ui-color-accent)]';
  }
}

export function feedbackIconClass(tone: FeedbackTone): string {
  switch (tone) {
    case 'success':
      return 'text-[var(--ui-color-success)]';
    case 'warning':
      return 'text-[var(--ui-color-warning)]';
    case 'error':
      return 'text-[var(--ui-color-danger)]';
    default:
      return 'text-[var(--ui-color-accent)]';
  }
}

export function createFeedbackRecord(
  id: string,
  input: FeedbackInput,
): FeedbackRecord {
  return {
    ...input,
    announcement: input.announcement ?? 'polite',
    id,
  };
}

function replaceMatchingFeedback(
  records: readonly FeedbackRecord[],
  feedback: FeedbackRecord,
): FeedbackRecord[] | null {
  if (!feedback.dedupeKey) return null;
  const matchingIndex = records.findIndex(
    (item) => item.dedupeKey === feedback.dedupeKey,
  );
  if (matchingIndex < 0) return null;
  const next = [...records];
  next[matchingIndex] = feedback;
  return next;
}

export function enqueueFeedback(
  current: FeedbackQueue,
  feedback: FeedbackRecord,
): FeedbackQueue {
  const replacedVisible = replaceMatchingFeedback(current.visible, feedback);
  if (replacedVisible) return { ...current, visible: replacedVisible };
  const replacedPending = replaceMatchingFeedback(current.pending, feedback);
  if (replacedPending) return { ...current, pending: replacedPending };
  if (current.visible.length < FEEDBACK_VISIBLE_LIMIT) {
    return { ...current, visible: [...current.visible, feedback] };
  }
  return {
    ...current,
    pending: [...current.pending, feedback].slice(-FEEDBACK_PENDING_LIMIT),
  };
}

export function dismissFeedback(
  current: FeedbackQueue,
  feedbackId: string,
): FeedbackQueue {
  const visibleIndex = current.visible.findIndex((item) => item.id === feedbackId);
  if (visibleIndex >= 0) {
    const nextVisible = current.visible.filter((item) => item.id !== feedbackId);
    const [promoted, ...remainingPending] = current.pending;
    return {
      visible: promoted ? [...nextVisible, promoted] : nextVisible,
      pending: remainingPending,
    };
  }
  const nextPending = current.pending.filter((item) => item.id !== feedbackId);
  return nextPending.length === current.pending.length
    ? current
    : { ...current, pending: nextPending };
}
