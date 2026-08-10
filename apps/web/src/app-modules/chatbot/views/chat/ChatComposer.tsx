import { FormEvent, ReactNode, useCallback, useState } from 'react';
import { ArrowUp, Loader2, Square } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { NavItem } from '@/src/app/shell/navigation-types';
import {
  clampSelectedSlashIndex,
  getChatComposerKeyIntent,
  isChatSendDisabled,
  isSlashCommandOpen,
  shouldSubmitChatForm,
} from './chat-composer-model';
import { SlashCommandMenu } from './SlashCommandMenu';
import { useSlashCommandItems } from './slash-command-items';

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
  /**
   * Pills/buttons rendered in the bottom-left of the composer card
   * (Claude.ai-style). Use this slot for the model picker, scope picker,
   * attachment buttons, etc. Send button stays bottom-right.
   */
  leadingControls?: ReactNode;
}

export function ChatComposer(props: ChatComposerProps) {
  const { t } = useTranslation('apps');
  const slashItems = useSlashCommandItems(props.toolItems ?? [], props.input);
  // Only treat the buffer as a slash command when there's at least one
  // matching tool. Inputs that pattern-match a command but have no matches
  // (e.g. `/tmp`, `/etc`, typos like `/fmexx`) fall through to normal chat
  // submission so users can still send literal slash-prefixed prompts.
  const isSlashOpen = isSlashCommandOpen(slashItems);
  const [slashIndex, setSlashIndex] = useState(0);
  const selectedSlashIndex = clampSelectedSlashIndex(
    slashIndex,
    slashItems?.length ?? 0,
  );

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      // Guard mouse/button submit paths so slash mode never leaks into the
      // chat stream while a slash command is being composed
      // must not send the raw slash-command buffer as a message.
      if (!shouldSubmitChatForm({ isSlashOpen })) {
        return;
      }
      props.onSubmit();
    },
    [isSlashOpen, props],
  );

  const handleToolSelect = useCallback(
    (item: NavItem) => {
      props.onSelectTool?.(item);
      // Always clear the slash buffer so the menu closes even if the caller
      // chose not to route (e.g. in tests without a router).
      props.onInputChange('');
    },
    [props],
  );

  const sendDisabled = isChatSendDisabled({
    input: props.input,
    isDisabled: props.isDisabled,
    isSlashOpen,
  });

  return (
    <form className="relative w-full" onSubmit={handleSubmit}>
      {props.chatError && (
        <div className="mb-3 rounded-md border border-app-danger-border bg-app-danger-bg px-3 py-2 app-text-body-sm text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
          {props.chatError}
        </div>
      )}
      <div className="relative">
        {isSlashOpen && slashItems ? (
          <SlashCommandMenu
            items={slashItems}
            selectedIndex={selectedSlashIndex}
            onSelect={handleToolSelect}
            onHighlight={setSlashIndex}
          />
        ) : null}
        {/* Claude.ai-style composer card: textarea on top, controls row at
            the bottom. The whole thing reads as one input — controls and
            send button live inside the same rounded border. */}
        <div className="flex flex-col rounded-2xl border border-app-border bg-app-bg transition-colors focus-within:border-app-accent">
          <textarea
            aria-label={props.placeholder ?? t('ai.composerPlaceholder')}
            autoFocus={props.autoFocus}
            className="app-text-body-sm w-full resize-none bg-transparent px-4 pb-2 pt-3 text-app-ink outline-none placeholder:text-app-ink/40"
            disabled={props.isDisabled}
            onChange={(event) => props.onInputChange(event.target.value)}
            onKeyDown={(event) => {
              const intent = getChatComposerKeyIntent({
                input: props.input,
                isDisabled: props.isDisabled,
                isSending: props.isSending,
                isSlashOpen,
                key: event.key,
                selectedSlashIndex,
                shiftKey: event.shiftKey,
                slashItemCount: slashItems?.length ?? 0,
              });
              if (intent.type === 'none') {
                return;
              }
              event.preventDefault();
              if (intent.type === 'highlight-slash-index') {
                setSlashIndex(intent.index);
                return;
              }
              if (intent.type === 'clear-slash-input') {
                props.onInputChange('');
                return;
              }
              if (intent.type === 'select-slash-item' && slashItems) {
                handleToolSelect(slashItems[intent.index]);
                return;
              }
              if (intent.type === 'submit-chat') {
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={props.placeholder ?? t('ai.composerPlaceholder')}
            rows={props.rows ?? 2}
            value={props.input}
          />
          <div className="flex items-center gap-2 px-2 pb-2">
            <div className="flex flex-1 flex-wrap items-center gap-2 min-w-0">
              {props.leadingControls}
            </div>
            {props.isSending && props.isStreaming ? (
              <button
                aria-label={t('ai.stop')}
                className="flex size-8 shrink-0 items-center justify-center rounded-full border border-app-border bg-app-surface text-app-ink transition-colors hover:border-app-accent"
                onClick={props.onAbort}
                type="button"
              >
                <Square size={14} />
              </button>
            ) : props.isSending ? (
              <button
                aria-label={t('ai.processing')}
                className="flex size-8 shrink-0 items-center justify-center rounded-full border border-app-border bg-app-surface text-app-ink/70"
                disabled
                type="button"
              >
                <Loader2 size={14} className="animate-spin" />
              </button>
            ) : (
              <button
                aria-label={t('ai.send')}
                className="flex size-8 shrink-0 items-center justify-center rounded-full bg-app-accent text-app-accent-fg transition-colors hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
                disabled={sendDisabled}
                type="submit"
              >
                <ArrowUp size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </form>
  );
}
