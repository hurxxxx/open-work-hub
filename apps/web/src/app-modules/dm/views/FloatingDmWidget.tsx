import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { DmThreadScrollSnapshotsRef } from './DMView';

import { Loader2 } from 'lucide-react';

import {
  DM_REALTIME_EVENT_TYPES,
  normalizeDmRealtimeEvent,
  upsertDmConversation,
} from '@open-work-hub/contracts/dm';

import {
  useRealtime,
  useRealtimeEvent,
} from '@/src/platform/realtime/realtime-provider';

import { listDmThreads, type DmThread } from '../api/dm-api';

const DMEmbeddedView = lazy(() =>
  import('./DMView').then((module) => ({ default: module.DMEmbeddedView })),
);

const DM_REALTIME_TYPES = [
  DM_REALTIME_EVENT_TYPES.messageCreated,
  DM_REALTIME_EVENT_TYPES.conversationCreated,
  DM_REALTIME_EVENT_TYPES.conversationUpdated,
  DM_REALTIME_EVENT_TYPES.conversationRead,
  DM_REALTIME_EVENT_TYPES.conversationRemoved,
] as const;

export function FloatingDmWidget({
  onThreadIdChange,
  reloadSeq = 0,
  threadScrollSnapshotsRef,
  threadId: controlledThreadId,
}: {
  onThreadIdChange?: (threadId: string) => void;
  reloadSeq?: number;
  threadScrollSnapshotsRef?: DmThreadScrollSnapshotsRef;
  threadId?: string;
}) {
  const [localThreadId, setLocalThreadId] = useState('');
  const threadId = controlledThreadId ?? localThreadId;
  const setThreadId = onThreadIdChange ?? setLocalThreadId;

  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center text-app-ink/40">
          <Loader2 aria-hidden="true" className="animate-spin" size={20} />
        </div>
      }
    >
      <DMEmbeddedView
        embeddedPersistentList
        onThreadIdChange={setThreadId}
        reloadSeq={reloadSeq}
        threadScrollSnapshotsRef={threadScrollSnapshotsRef}
        threadId={threadId}
      />
    </Suspense>
  );
}

export function useFloatingDmUnreadCount(
  token: string | null,
  reloadSeq = 0,
): number {
  const { reconnectSeq } = useRealtime();
  const [threads, setThreads] = useState<DmThread[]>([]);
  const unreadCount = useMemo(
    () =>
      threads.reduce(
        (count, thread) => count + Math.max(0, thread.unread_count),
        0,
      ),
    [threads],
  );
  const reloadThreads = useCallback(async () => {
    if (!token) {
      setThreads([]);
      return;
    }
    try {
      const response = await listDmThreads(token);
      setThreads(response.items);
    } catch {
      return;
    }
  }, [token]);

  const applyRealtimeUnreadEvent = useCallback((event: unknown) => {
    const normalized = normalizeDmRealtimeEvent(event);
    if (!normalized) {
      return;
    }
    const conversation =
      normalized.data?.conversation ?? normalized.data?.thread ?? null;
    if (conversation) {
      setThreads((current) => upsertDmConversation(current, conversation));
      return;
    }
    if (normalized.type === DM_REALTIME_EVENT_TYPES.conversationRemoved) {
      const removedId =
        normalized.data?.conversation_id ?? normalized.data?.thread_id ?? null;
      if (removedId) {
        setThreads((current) =>
          current.filter((thread) => thread.id !== removedId),
        );
      }
    }
  }, []);

  useEffect(() => {
    void reloadThreads();
  }, [reconnectSeq, reloadSeq, reloadThreads]);

  useEffect(() => {
    if (!token) {
      return undefined;
    }
    const reloadWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        void reloadThreads();
      }
    };
    const intervalId = window.setInterval(() => {
      void reloadThreads();
    }, 60000);
    window.addEventListener('focus', reloadWhenVisible);
    document.addEventListener('visibilitychange', reloadWhenVisible);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', reloadWhenVisible);
      document.removeEventListener('visibilitychange', reloadWhenVisible);
    };
  }, [reloadThreads, token]);

  useRealtimeEvent(DM_REALTIME_TYPES[0], applyRealtimeUnreadEvent);
  useRealtimeEvent(DM_REALTIME_TYPES[1], applyRealtimeUnreadEvent);
  useRealtimeEvent(DM_REALTIME_TYPES[2], applyRealtimeUnreadEvent);
  useRealtimeEvent(DM_REALTIME_TYPES[3], applyRealtimeUnreadEvent);
  useRealtimeEvent(DM_REALTIME_TYPES[4], applyRealtimeUnreadEvent);

  return unreadCount;
}
