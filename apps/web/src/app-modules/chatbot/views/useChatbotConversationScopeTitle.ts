import { useEffect } from 'react';

import { getMeeting } from '@/src/app-modules/meeting/public-api';
import type { ChatbotViewState, ChatbotViewStateUpdater } from './useChatbotViewState';

export function useChatbotConversationScopeTitle({
  scopeInfo,
  setScopeInfo,
  token,
  workspaceSlug,
}: {
  scopeInfo: ChatbotViewState['scopeInfo'];
  setScopeInfo: (
    value: ChatbotViewStateUpdater<ChatbotViewState['scopeInfo']>,
  ) => void;
  token: string | null;
  workspaceSlug: string | undefined;
}) {
  useEffect(() => {
    if (!token || !workspaceSlug) return;
    if (
      !scopeInfo ||
      scopeInfo.ref !== 'meeting' ||
      scopeInfo.title !== null
    ) {
      return;
    }
    let cancelled = false;
    const resourceId = scopeInfo.resourceId;
    getMeeting(token, workspaceSlug, resourceId)
      .then((meeting) => {
        if (cancelled) return;
        setScopeInfo((prev) =>
          prev &&
          prev.ref === 'meeting' &&
          prev.resourceId === resourceId &&
          prev.title === null
            ? { ...prev, title: meeting.title }
            : prev,
        );
      })
      .catch(() => {
        // Silent fallback: the chip still renders with the generic label.
      });
    return () => {
      cancelled = true;
    };
  }, [setScopeInfo, token, workspaceSlug, scopeInfo]);
}
