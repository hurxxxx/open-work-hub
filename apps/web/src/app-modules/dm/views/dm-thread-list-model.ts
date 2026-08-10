import {
  buildDmConversationListItemProjection,
  dmConversationDisplayName,
  dmConversationPreviewText,
  dmInitials as projectDmInitials,
  dmMessagePreviewText as projectDmMessagePreviewText,
  dmUnreadBadge as projectDmUnreadBadge,
  dmUserDisplayName,
} from '@ai-do/contracts/dm';

import type { DmMessage, DmThread, DmUser } from '../api/dm-api';

export type TranslateDmLabel = (
  key: string,
  values?: Record<string, unknown>,
) => string;

export interface DmThreadListItem {
  active: boolean;
  id: string;
  initials: string;
  name: string;
  preview: string;
  unreadBadge: string | null;
}

export function displayDmUserName(user: DmUser): string {
  return dmUserDisplayName(user, 'DM');
}

export function dmThreadDisplayName(
  thread: DmThread,
  currentUserId: string | undefined,
): string {
  return dmConversationDisplayName(thread, {
    currentUserId,
    labels: {
      directFallback: 'DM',
      groupFallback: 'DM',
    },
  });
}

export function dmInitials(name: string): string {
  return projectDmInitials(name);
}

export function dmMessagePreviewText(
  message: DmMessage,
  translate: TranslateDmLabel,
): string {
  return projectDmMessagePreviewText(message, dmPreviewLabels(translate));
}

export function dmThreadPreviewText(
  thread: DmThread,
  translate: TranslateDmLabel,
): string {
  return dmConversationPreviewText(thread, {
    labels: dmPreviewLabels(translate),
    senderPrefix: 'group',
  });
}

export function dmUnreadBadge(count: number): string | null {
  return projectDmUnreadBadge(count);
}

export function buildDmThreadListItem({
  activeThreadId,
  currentUserId,
  thread,
  translate,
}: {
  activeThreadId: string;
  currentUserId: string | undefined;
  thread: DmThread;
  translate: TranslateDmLabel;
}): DmThreadListItem {
  const item = buildDmConversationListItemProjection({
    conversation: thread,
    currentUserId,
    labels: {
      ...dmPreviewLabels(translate),
      directFallback: 'DM',
      groupFallback: 'DM',
    },
    selectedConversationId: activeThreadId,
    senderPrefix: 'group',
  });
  return {
    active: item.selected,
    id: item.id,
    initials: item.initials,
    name: item.name,
    preview: item.preview,
    unreadBadge: item.unreadBadge,
  };
}

function dmPreviewLabels(translate: TranslateDmLabel) {
  return {
    emptyThread: translate('dm.emptyThread'),
    attachmentFile: (filename: string) =>
      translate('dm.attachmentPreviewFile', { filename }),
    attachmentCount: (count: number) =>
      translate('dm.attachmentPreviewCount', { count }),
  };
}
