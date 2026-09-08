import {
  createWhiteboardAccessRealtimeSubscriptionMessage,
  REALTIME_TOPIC_EVENT_TYPES,
} from '@open-work-hub/contracts/realtime';
import {
  Fragment,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import { useRealtime } from '@/src/platform/realtime/realtime-provider';

export function WhiteboardAccessBoundary({
  boardId,
  children,
  shareToken,
}: {
  boardId: string;
  children: (isCurrent: () => boolean) => ReactNode;
  shareToken: string | null;
}) {
  const { addEventListener, subscribe } = useRealtime();
  const revisionRef = useRef(0);
  const mountedRef = useRef(true);
  const [revision, setRevision] = useState(0);
  const isCurrent = useCallback(
    () => mountedRef.current && revisionRef.current === revision,
    [revision],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const unsubscribeListener = addEventListener(
      REALTIME_TOPIC_EVENT_TYPES.whiteboardAccessChanged,
      (event) => {
        const data = event.data;
        if (
          !data ||
          typeof data !== 'object' ||
          !('whiteboard_id' in data) ||
          data.whiteboard_id !== boardId
        ) {
          return;
        }
        // Discard this editor's scene, dialogs, queued writes, and outstanding
        // callbacks before a fresh instance rechecks the original access lens.
        revisionRef.current += 1;
        setRevision(revisionRef.current);
      },
    );
    const unsubscribeBoard = subscribe(
      createWhiteboardAccessRealtimeSubscriptionMessage({
        key: boardId,
        shareToken,
      }),
    );
    return () => {
      unsubscribeBoard();
      unsubscribeListener();
    };
  }, [addEventListener, boardId, shareToken, subscribe]);

  return <Fragment key={revision}>{children(isCurrent)}</Fragment>;
}
