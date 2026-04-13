import { useCallback, useEffect, useMemo, useState } from 'react';

import { listRecordingStaging, type RecordingStagingItem } from '@/src/domains/meeting/meeting-api';
import {
  buildSessionBlob,
  getChunks,
  listIncompleteSessions,
  type RecordingSessionState,
} from '@/src/domains/meeting/recording-db';

export interface RecoverySessionItem {
  stagingId: string;
  localSession: RecordingSessionState | null;
  remoteStaging: RecordingStagingItem | null;
  localBlob: Blob | null;
  previewUrl: string | null;
  localBytes: number;
  uploadedLocalBytes: number;
}

function sumChunkBytes(blobs: Blob[]): number {
  return blobs.reduce((total, blob) => total + blob.size, 0);
}

export function useRecordingRecovery(meetingId: string, token: string | null) {
  const [items, setItems] = useState<RecoverySessionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [localSessions, remoteSessions] = await Promise.all([
        listIncompleteSessions(meetingId),
        token ? listRecordingStaging(token, meetingId) : Promise.resolve([]),
      ]);
      const localById = new Map<string, RecordingSessionState>();
      for (const session of localSessions) {
        localById.set(session.stagingId, session);
      }
      const remoteById = new Map<string, RecordingStagingItem>();
      for (const session of remoteSessions) {
        remoteById.set(session.id, session);
      }

      const sessionIds = Array.from(new Set([...localById.keys(), ...remoteById.keys()]));
      const nextItems: RecoverySessionItem[] = [];
      for (const stagingId of sessionIds) {
        const localSession = localById.get(stagingId) ?? null;
        const remoteStaging = remoteById.get(stagingId) ?? null;
        const chunks = localSession ? await getChunks(stagingId) : [];
        const localBlob = localSession ? await buildSessionBlob(stagingId) : null;
        nextItems.push({
          stagingId,
          localSession,
          remoteStaging,
          localBlob,
          previewUrl: localBlob ? URL.createObjectURL(localBlob) : null,
          localBytes: sumChunkBytes(chunks.map((chunk) => chunk.blob)),
          uploadedLocalBytes: sumChunkBytes(
            chunks.filter((chunk) => chunk.uploadedAt != null).map((chunk) => chunk.blob),
          ),
        });
      }
      setItems(nextItems.sort((left, right) => {
        const leftTs = left.localSession?.startedAt ?? Date.parse(left.remoteStaging?.started_at ?? '0');
        const rightTs = right.localSession?.startedAt ?? Date.parse(right.remoteStaging?.started_at ?? '0');
        return rightTs - leftTs;
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '복구 가능한 녹음을 확인할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }, [meetingId, token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => () => {
    items.forEach((item) => {
      if (item.previewUrl) {
        URL.revokeObjectURL(item.previewUrl);
      }
    });
  }, [items]);

  const grouped = useMemo(() => items, [items]);

  return {
    items: grouped,
    loading,
    error,
    refresh,
  };
}
