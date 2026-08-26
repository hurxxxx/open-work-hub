import * as ToastPrimitive from '@radix-ui/react-toast';
import { CircleCheck, CircleX, Info, TriangleAlert, X } from 'lucide-react';
import {
  createContext,
  use,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { cn } from '../utils/cn';
import {
  createFeedbackRecord,
  dismissFeedback,
  EMPTY_FEEDBACK_QUEUE,
  enqueueFeedback,
  FEEDBACK_DURATION_MS,
  feedbackIconClass,
  feedbackToneClass,
  type FeedbackInput,
  type FeedbackQueue,
  type FeedbackRecord,
  type FeedbackTone,
} from './feedback-state';

export interface FeedbackApi {
  show: (input: FeedbackInput) => void;
  info: (title: string, description?: string) => void;
  success: (title: string, description?: string) => void;
  warning: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

export interface FeedbackLabels {
  close: string;
  item: string;
  region: string;
}

const FeedbackContext = createContext<FeedbackApi | null>(null);

function FeedbackIcon({ tone }: { tone: FeedbackTone }) {
  const props = {
    'aria-hidden': true,
    className: cn('mt-0.5 shrink-0', feedbackIconClass(tone)),
    size: 17,
    strokeWidth: 2.1,
  } as const;
  switch (tone) {
    case 'success':
      return <CircleCheck {...props} />;
    case 'warning':
      return <TriangleAlert {...props} />;
    case 'error':
      return <CircleX {...props} />;
    default:
      return <Info {...props} />;
  }
}

function FeedbackItem({
  feedback,
  closeLabel,
  onDismiss,
}: {
  feedback: FeedbackRecord;
  closeLabel: string;
  onDismiss: (feedbackId: string) => void;
}) {
  return (
    <ToastPrimitive.Root
      className={cn(
        'relative grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-ui-surface-raised py-3 pl-3 pr-10 text-[var(--ui-color-ink)] shadow-[var(--ui-shadow-lg)] outline-none transition-transform duration-[var(--ui-motion-base)] motion-reduce:transition-none data-[swipe=cancel]:translate-x-0 data-[swipe=end]:translate-x-[var(--radix-toast-swipe-end-x)] data-[swipe=move]:translate-x-[var(--radix-toast-swipe-move-x)]',
        feedbackToneClass(feedback.tone),
      )}
      duration={
        feedback.action ? Number.POSITIVE_INFINITY : FEEDBACK_DURATION_MS
      }
      onOpenChange={(open) => {
        if (!open) onDismiss(feedback.id);
      }}
      open
      type={feedback.announcement === 'assertive' ? 'foreground' : 'background'}
    >
      <FeedbackIcon tone={feedback.tone} />
      <div className="min-w-0">
        <ToastPrimitive.Title className="text-[length:var(--ui-text-body-sm)] font-semibold leading-snug">
          {feedback.title}
        </ToastPrimitive.Title>
        {feedback.description ? (
          <ToastPrimitive.Description className="mt-0.5 text-[length:var(--ui-text-caption)] leading-snug text-[var(--ui-color-ink-muted)]">
            {feedback.description}
          </ToastPrimitive.Description>
        ) : null}
      </div>
      {feedback.action ? (
        <div className="col-start-2 flex justify-end">
          <ToastPrimitive.Action
            altText={feedback.action.altText}
            className="inline-flex h-[var(--ui-density-dense)] items-center justify-center rounded-[var(--ui-radius-sm)] border border-[var(--ui-color-border)] bg-ui-surface-subtle px-2.5 text-[length:var(--ui-text-caption)] font-semibold text-[var(--ui-color-ink)] transition-colors hover:bg-ui-accent-weak focus:outline-none focus:ring-2 focus:ring-[var(--ui-color-accent)]/25"
            onClick={feedback.action.onAction}
          >
            {feedback.action.label}
          </ToastPrimitive.Action>
        </div>
      ) : null}
      <ToastPrimitive.Close
        aria-label={closeLabel}
        className="absolute right-2 top-2 inline-flex size-7 items-center justify-center rounded-[var(--ui-radius-sm)] text-current/60 transition-colors hover:bg-ui-surface-subtle hover:text-current focus:outline-none focus:ring-2 focus:ring-[var(--ui-color-accent)]/25"
        title={closeLabel}
      >
        <X aria-hidden="true" size={15} strokeWidth={2.2} />
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
}

export function FeedbackProvider({
  children,
  labels,
}: {
  children: ReactNode;
  labels: FeedbackLabels;
}) {
  const [queue, setQueue] = useState<FeedbackQueue>(EMPTY_FEEDBACK_QUEUE);
  const nextId = useRef(0);
  const api = useMemo<FeedbackApi>(() => {
    const show = (input: FeedbackInput) => {
      const id = `feedback-${Date.now()}-${++nextId.current}`;
      setQueue((current) =>
        enqueueFeedback(current, createFeedbackRecord(id, input)),
      );
    };
    const showTone = (
      tone: FeedbackTone,
      title: string,
      description?: string,
    ) =>
      show({
        announcement: tone === 'error' ? 'assertive' : 'polite',
        description,
        title,
        tone,
      });
    return {
      show,
      info: (title, description) => showTone('info', title, description),
      success: (title, description) => showTone('success', title, description),
      warning: (title, description) => showTone('warning', title, description),
      error: (title, description) => showTone('error', title, description),
    };
  }, []);
  const dismiss = (feedbackId: string) => {
    setQueue((current) => dismissFeedback(current, feedbackId));
  };
  return (
    <FeedbackContext.Provider value={api}>
      <ToastPrimitive.Provider
        duration={FEEDBACK_DURATION_MS}
        label={labels.item}
        swipeDirection="right"
      >
        {children}
        {queue.visible.map((feedback) => (
          <FeedbackItem
            closeLabel={labels.close}
            feedback={feedback}
            key={feedback.id}
            onDismiss={dismiss}
          />
        ))}
        <ToastPrimitive.Viewport
          className="fixed right-4 top-4 z-[var(--ui-z-toast)] grid w-[min(380px,calc(100vw-2rem))] gap-2 outline-none"
          label={labels.region}
        />
      </ToastPrimitive.Provider>
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): FeedbackApi {
  const context = use(FeedbackContext);
  if (!context) throw new Error('useFeedback must be used within FeedbackProvider');
  return context;
}

export type {
  FeedbackAction,
  FeedbackAnnouncement,
  FeedbackInput,
  FeedbackTone,
} from './feedback-state';
