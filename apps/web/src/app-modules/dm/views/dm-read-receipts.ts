import type { DmThread } from '../api/dm-api';
import {
  visibleDmThreadReadConversationId,
  type DmReadPresenceInput,
} from './dm-conversation-runtime-model';

export interface DmReadReceiptBrowser {
  hasFocus: () => boolean;
  visibilityState: string;
}

export interface MarkDmThreadReadInput {
  conversationId: string | null | undefined;
  markThreadRead: (token: string, conversationId: string) => Promise<DmThread>;
  onThreadRead: (thread: DmThread) => void;
  token: string | null | undefined;
}

export interface MarkVisibleDmThreadReadInput extends Omit<MarkDmThreadReadInput, 'conversationId'> {
  presence: DmReadPresenceInput;
  selectedThreadId: string | null | undefined;
}

export function currentDmReadPresenceFromBrowser(
  browser: DmReadReceiptBrowser,
): DmReadPresenceInput {
  return {
    visible: browser.visibilityState === 'visible',
    focused: browser.hasFocus(),
  };
}

export async function markDmThreadReadAndApply({
  conversationId,
  markThreadRead,
  onThreadRead,
  token,
}: MarkDmThreadReadInput): Promise<DmThread | null> {
  if (!token || !conversationId) {
    return null;
  }
  const thread = await markThreadRead(token, conversationId);
  onThreadRead(thread);
  return thread;
}

export async function markVisibleDmThreadReadAndApply({
  markThreadRead,
  onThreadRead,
  presence,
  selectedThreadId,
  token,
}: MarkVisibleDmThreadReadInput): Promise<DmThread | null> {
  const conversationId = visibleDmThreadReadConversationId({
    authenticated: Boolean(token),
    selectedThreadId,
    ...presence,
  });
  return markDmThreadReadAndApply({
    conversationId,
    markThreadRead,
    onThreadRead,
    token,
  });
}
