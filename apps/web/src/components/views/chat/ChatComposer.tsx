import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Loader2, Send, Square } from 'lucide-react';

import { NAV_ITEMS, type NavItem } from '@/src/constants';
import {
  SlashCommandMenu,
  useSlashCommandItems,
} from '@/src/components/views/chat/SlashCommandMenu';

export interface ChatComposerProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onAbort: () => void;
  isSending: boolean;
  isStreaming: boolean;
  chatError: string | null;
  onSelectTool?: (item: NavItem) => void;
  /**
   * Candidate list for the `/` slash command menu. Callers should pass a
   * workspace-scoped list (e.g. merged from workspaceBootstrap.data.nav) so
   * disabled/unauthorized tools don't appear. Defaults to the full NAV_ITEMS
   * AI slice for test/storybook contexts where no workspace is available.
   */
  toolItems?: NavItem[];
  placeholder?: string;
  rows?: number;
  autoFocus?: boolean;
  isDisabled?: boolean;
}

const DEFAULT_TOOL_ITEMS = NAV_ITEMS.filter((item) => item.appId === 'ai');

export function ChatComposer(props: ChatComposerProps) {
  const slashItems = useSlashCommandItems(
    props.toolItems ?? DEFAULT_TOOL_ITEMS,
    props.input,
  );
  // Only treat the buffer as a slash command when there's at least one
  // matching tool. Inputs that pattern-match a command but have no matches
  // (e.g. `/tmp`, `/etc`, typos like `/fmexx`) fall through to normal chat
  // submission so users can still send literal slash-prefixed prompts.
  const isSlashOpen = slashItems !== null && slashItems.length > 0;
  const [slashIndex, setSlashIndex] = useState(0);

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      // Guard mouse/button submit paths so slash mode never leaks into the
      // chat stream — pressing 전송 while a slash command is being composed
      // must not send the raw "/fmea" buffer as a message.
      if (isSlashOpen) {
        return;
      }
      props.onSubmit();
    },
    [isSlashOpen, props],
  );

  useEffect(() => {
    // Reset highlight whenever the candidate list changes.
    setSlashIndex(0);
  }, [slashItems]);

  const handleToolSelect = useCallback(
    (item: NavItem) => {
      props.onSelectTool?.(item);
      // Always clear the slash buffer so the menu closes even if the caller
      // chose not to route (e.g. in tests without a router).
      props.onInputChange('');
    },
    [props],
  );

  return (
    <form className="relative w-full" onSubmit={handleSubmit}>
      {props.chatError && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 app-text-body-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {props.chatError}
        </div>
      )}
      <div className="relative flex min-h-12 gap-3">
        {isSlashOpen && slashItems ? (
          <SlashCommandMenu
            items={slashItems}
            selectedIndex={
              slashItems.length === 0
                ? 0
                : Math.min(slashIndex, slashItems.length - 1)
            }
            onSelect={handleToolSelect}
            onHighlight={setSlashIndex}
          />
        ) : null}
        <textarea
          autoFocus={props.autoFocus}
          className="app-text-body-sm min-h-12 flex-1 resize-none rounded-lg border border-app-border bg-app-bg px-4 py-3 text-app-ink outline-none transition-colors placeholder:text-gray-400 focus:border-app-accent"
          disabled={props.isSending || props.isDisabled}
          onChange={(event) => props.onInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (isSlashOpen && slashItems) {
              if (event.key === 'ArrowDown' && slashItems.length > 0) {
                event.preventDefault();
                setSlashIndex(
                  (current) => (current + 1) % slashItems.length,
                );
                return;
              }
              if (event.key === 'ArrowUp' && slashItems.length > 0) {
                event.preventDefault();
                setSlashIndex((current) =>
                  current <= 0 ? slashItems.length - 1 : current - 1,
                );
                return;
              }
              if (event.key === 'Escape') {
                event.preventDefault();
                props.onInputChange('');
                return;
              }
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (slashItems.length === 0) {
                  // No match → silently swallow Enter so the slash buffer
                  // never submits as a chat message.
                  return;
                }
                const clamped = Math.min(slashIndex, slashItems.length - 1);
                handleToolSelect(slashItems[clamped]);
                return;
              }
            }
            if (event.key !== 'Enter' || event.shiftKey) {
              return;
            }
            event.preventDefault();
            // Mirror the send-button disabled rule so keyboard submit cannot
            // diverge from the visible button state if the component is
            // reused outside AIView's handleSubmit guard.
            if (!props.input.trim() || props.isSending || props.isDisabled) {
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
          disabled={!props.input.trim() || isSlashOpen || props.isDisabled}
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
