import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listRecordingStaging, type RecordingStagingItem } from '../../api/meeting-api';
import {
  buildSessionBlob,
  getChunks,
  listIncompleteSessions,
  type RecordingSessionState,
} from '../../api/recording-db';

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

export function useRecordingRecovery(
  workspaceSlug: string,
  meetingId: string,
  token: string | null,
) {
  const { t } = useTranslation('apps');
  const [items, setItems] = useState<RecoverySessionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [localSessions, remoteSessions] = await Promise.all([
        listIncompleteSessions(meetingId),
        token
          ? listRecordingStaging(token, workspaceSlug, meetingId)
          : Promise.resolve([]),
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
      setError(err instanceof Error ? err.message : t('meeting.recordingErrors.recoveryCheckFailed'));
    } finally {
      setLoading(false);
    }
  }, [meetingId, t, token, workspaceSlug]);

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
