import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { listRecordingUploads, type RecordingUpload } from '../api/recording-api';
import {
  buildRecordingScopeKey,
  buildSessionBlob,
  getChunks,
  listIncompleteSessions,
  type RecordingTargetRef,
  type RecordingSessionState,
} from './recording-session-db';

export interface RecoverySessionItem {
  stagingId: string;
  localSession: RecordingSessionState | null;
  remoteStaging: RecordingUpload | null;
  localBlob: Blob | null;
  previewUrl: string | null;
  localBytes: number;
  uploadedLocalBytes: number;
}

function sumChunkBytes(blobs: Blob[]): number {
  return blobs.reduce((total, blob) => total + blob.size, 0);
}

export function useRecordingRecovery({
  workspaceSlug,
  token,
  initialTarget = null,
}: {
  workspaceSlug: string;
  token: string | null;
  initialTarget?: RecordingTargetRef | null;
}) {
  const { t } = useTranslation('apps');
  const [items, setItems] = useState<RecoverySessionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scopeKey = useMemo(
    () => buildRecordingScopeKey(workspaceSlug, initialTarget),
    [initialTarget, workspaceSlug],
  );

  const refresh = useCallback(async () => {
    if (!workspaceSlug) {
      setItems([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [localSessions, remoteSessions] = await Promise.all([
        listIncompleteSessions({
          workspaceSlug,
          scopeKey: initialTarget ? scopeKey : null,
        }),
        token
          ? listRecordingUploads(token, workspaceSlug, initialTarget
            ? {
                initial_target_app: initialTarget.app,
                initial_target_type: initialTarget.type,
                initial_target_id: initialTarget.id,
              }
            : {})
          : Promise.resolve([]),
      ]);
      const localById = new Map<string, RecordingSessionState>();
      for (const session of localSessions) {
        localById.set(session.stagingId, session);
      }
      const remoteById = new Map<string, RecordingUpload>();
      for (const session of remoteSessions) {
        remoteById.set(session.id, session);
      }

      const sessionIds = Array.from(new Set([...localById.keys(), ...remoteById.keys()]));
      const nextItems = await Promise.all(sessionIds.map(async (stagingId) => {
        const localSession = localById.get(stagingId) ?? null;
        const remoteStaging = remoteById.get(stagingId) ?? null;
        const [chunks, localBlob] = localSession
          ? await Promise.all([getChunks(stagingId), buildSessionBlob(stagingId)])
          : [[], null] as const;
        return {
          stagingId,
          localSession,
          remoteStaging,
          localBlob,
          previewUrl: localBlob ? URL.createObjectURL(localBlob) : null,
          localBytes: sumChunkBytes(chunks.map((chunk) => chunk.blob)),
          uploadedLocalBytes: sumChunkBytes(
            chunks.filter((chunk) => chunk.uploadedAt != null).map((chunk) => chunk.blob),
          ),
        };
      }));
      setItems(nextItems.sort((left, right) => {
        const leftTs = left.localSession?.startedAt ?? Date.parse(left.remoteStaging?.started_at ?? '0');
        const rightTs = right.localSession?.startedAt ?? Date.parse(right.remoteStaging?.started_at ?? '0');
        return rightTs - leftTs;
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('recording.errors.recoveryCheckFailed'));
    } finally {
      setLoading(false);
    }
  }, [initialTarget, scopeKey, t, token, workspaceSlug]);

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
