import {
  BlockEditor,
  BlockViewer,
  CollaborativeBlockEditor,
  type BlockContent,
} from '@open-work-hub/ui';
import { Pencil } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  getDocsCollabSession,
  makeDocsPageRef,
  saveDocsCollabSnapshot,
  type DocsPageItem,
} from '../api/docs-api';
import { useDocsCollabSnapshotSaveController } from './useDocsCollabSnapshotSaveController';

interface DocsBlockContentSurfaceProps {
  page: DocsPageItem;
  canEdit: boolean;
  token?: string | null;

  shareToken?: string | null;
  contentEditorVersion?: number;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  onStandaloneBlocksChange: (
    pageId: string,
    blocks: Record<string, unknown>[],
  ) => void;
  onCollaborativeBlocksChange: (
    pageId: string,
    blocks: Record<string, unknown>[],
  ) => void;
}

export function DocsBlockContentSurface({
  page,
  canEdit,
  token,
  shareToken,
  contentEditorVersion = 0,
  uploadFile,
  resolveFileUrl,
  onStandaloneBlocksChange,
  onCollaborativeBlocksChange,
}: DocsBlockContentSurfaceProps) {
  const { t } = useTranslation(['apps']);
  const [editingCollabPageId, setEditingCollabPageId] = useState<string | null>(
    null,
  );
  const pageRef = useMemo(
    () => makeDocsPageRef(page.source_type, page.source_page_id),
    [page.source_page_id, page.source_type],
  );
  const { queueSnapshotSave } = useDocsCollabSnapshotSaveController({
    token,
    saveSnapshot: saveDocsCollabSnapshot,
  });

  useEffect(() => {
    setEditingCollabPageId(null);
  }, [page.id]);

  const blockContent = (page.content_blocks ?? []) as BlockContent;
  const surfaceKey = `${page.id}:${contentEditorVersion}`;
  const canStartRealtimeEditing =
    canEdit && page.realtime_collab && !shareToken && Boolean(token);

  const loadCollabSession = useCallback(async () => {
    if (!token) {
      throw new Error(t('apps:docs.collab.startFailed'));
    }
    const session = await getDocsCollabSession(token, pageRef);
    return {
      roomKey: session.room_key,
      wsPath: session.ws_path,
      user: {
        id: session.user.id,
        fullName: session.user.full_name,
      },
      realtimeStatus: session.realtime_status,
      readOnlyReason: session.read_only_reason,
      snapshotContent: (session.snapshot_content_blocks ?? []) as never,
      yjsState: session.yjs_state,
    };
  }, [pageRef, t, token]);

  if (canStartRealtimeEditing && token && editingCollabPageId === page.id) {
    return (
      <CollaborativeBlockEditor
        sessionKey={surfaceKey}
        authToken={token}
        loadSession={loadCollabSession}
        messages={{
          permissionRevoked: t('apps:docs.collab.permissionRevoked'),
          relayUnavailable: t('apps:docs.collab.relayUnavailable'),
          startFailed: t('apps:docs.collab.startFailed'),
          preparing: t('apps:docs.collab.preparing'),
          tooManyConnections: t('apps:docs.collab.tooManyConnections'),
        }}
        placeholder={t('apps:docs.startWriting')}
        uploadFile={uploadFile}
        resolveFileUrl={resolveFileUrl}
        contentOverride={blockContent}
        contentOverrideVersion={contentEditorVersion}
        onChange={(content, metadata) => {
          const blocks = content as Record<string, unknown>[];
          onCollaborativeBlocksChange(page.id, blocks);
          queueSnapshotSave(pageRef, blocks, metadata.yjsState);
        }}
      />
    );
  }

  if (canStartRealtimeEditing && token) {
    return (
      <div className="space-y-3">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setEditingCollabPageId(page.id)}
            className="inline-flex items-center gap-2 rounded-md bg-app-accent px-3 py-1.5 text-[length:var(--ui-text-control)] font-medium text-app-accent-fg hover:opacity-90"
          >
            <Pencil size={14} />
            {t('apps:docs.startEditing')}
          </button>
        </div>
        <BlockViewer
          key={`${surfaceKey}:readonly`}
          content={blockContent}
          resolveFileUrl={resolveFileUrl}
        />
      </div>
    );
  }

  if (canEdit) {
    return (
      <BlockEditor
        key={surfaceKey}
        initialContent={blockContent}
        placeholder={t('apps:docs.startWriting')}
        uploadFile={uploadFile}
        resolveFileUrl={resolveFileUrl}
        onChange={(content) =>
          onStandaloneBlocksChange(
            page.id,
            content as Record<string, unknown>[],
          )
        }
      />
    );
  }

  return (
    <BlockViewer
      key={surfaceKey}
      content={blockContent}
      resolveFileUrl={resolveFileUrl}
    />
  );
}
