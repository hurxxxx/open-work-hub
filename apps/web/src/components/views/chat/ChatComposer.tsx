import { FormEvent, useCallback } from 'react';
import { Loader2, Send, Square } from 'lucide-react';

export interface ChatComposerProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onAbort: () => void;
  isSending: boolean;
  isStreaming: boolean;
  chatError: string | null;
  placeholder?: string;
  rows?: number;
  autoFocus?: boolean;
}

export function ChatComposer(props: ChatComposerProps) {
  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      props.onSubmit();
    },
    [props],
  );

  return (
    <form className="w-full" onSubmit={handleSubmit}>
      {props.chatError && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 app-text-body-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {props.chatError}
        </div>
      )}
      <div className="flex min-h-12 gap-3">
        <textarea
          autoFocus={props.autoFocus}
          className="app-text-body-sm min-h-12 flex-1 resize-none rounded-lg border border-app-border bg-app-bg px-4 py-3 text-app-ink outline-none transition-colors placeholder:text-gray-400 focus:border-app-accent"
          disabled={props.isSending}
          onChange={(event) => props.onInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Enter' || event.shiftKey) {
              return;
            }
            event.preventDefault();
            // Mirror the send-button disabled rule so keyboard submit cannot
            // diverge from the visible button state if the component is
            // reused outside AIView's handleSubmit guard.
            if (!props.input.trim() || props.isSending) {
              return;
            }
            event.currentTarget.form?.requestSubmit();
          }}
          placeholder={props.placeholder ?? '메시지를 입력하세요'}
          rows={props.rows ?? 2}
          value={props.input}
        />
        {props.isSending && props.isStreaming ? (
          <button
            className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg border border-app-border bg-app-surface px-4 text-app-ink transition-colors hover:border-app-accent"
            onClick={props.onAbort}
            type="button"
          >
            <Square size={16} />
            <span className="hidden sm:inline">중단</span>
          </button>
        ) : props.isSending ? (
          <button
            className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg border border-app-border bg-app-surface px-4 text-app-ink/70"
            disabled
            type="button"
          >
            <Loader2 size={16} className="animate-spin" />
            <span className="hidden sm:inline">처리 중</span>
          </button>
        ) : (
          <button
            className="app-text-control flex h-12 shrink-0 items-center gap-2 rounded-lg bg-app-accent px-4 text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!props.input.trim()}
            type="submit"
          >
            <Send size={16} />
            <span className="hidden sm:inline">전송</span>
          </button>
        )}
      </div>
    </form>
  );
}
