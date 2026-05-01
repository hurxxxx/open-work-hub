import { useEffect, useMemo, useRef, useState } from 'react';
import { MantineProvider } from '@mantine/core';
import { BlockNoteEditor } from '@blocknote/core';
import { blocksToYDoc } from '@blocknote/core/yjs';
import { BlockNoteView } from '@blocknote/mantine';
import { useCreateBlockNote } from '@blocknote/react';
import { Loader2 } from 'lucide-react';
import { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';
import '@mantine/core/styles.css';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';

import { BlockViewer } from './block-viewer';
import { fullSchema } from './schema';
import { useResolvedTheme } from './use-theme';
import type { BlockContent } from './types';

type CollaborativeSession = {
  roomKey: string;
  wsPath: string;
  user: {
    id: string;
    fullName: string;
  };
  realtimeStatus: 'enabled' | 'degraded';
  readOnlyReason: 'relay_unavailable' | 'permission_revoked' | null;
  snapshotContent: BlockContent | null;
  yjsState: string | null;
};

export interface CollaborativeBlockEditorProps {
  sessionKey: string;
  authToken: string;
  loadSession: () => Promise<CollaborativeSession>;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  onChange?: (content: BlockContent) => void;
}

const USER_COLORS = [
  '#0ea5e9',
  '#ef4444',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#14b8a6',
  '#f97316',
] as const;

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(index);
    hash |= 0;
  }
  return Math.abs(hash);
}

function colorForUser(userId: string): string {
  return USER_COLORS[hashString(userId) % USER_COLORS.length];
}

function decodeBase64ToUint8Array(value: string): Uint8Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function toWebSocketUrl(wsPath: string): string {
  const resolved = new URL(wsPath, window.location.origin);
  resolved.protocol = resolved.protocol === 'https:' ? 'wss:' : 'ws:';
  return resolved.toString();
}

function resolveReadOnlyMessage(reason: 'relay_unavailable' | 'permission_revoked' | null): string {
  if (reason === 'permission_revoked') {
    return '문서 편집 권한이 회수되어 읽기 전용으로 전환되었습니다.';
  }
  return '실시간 협업 relay를 사용할 수 없어 읽기 전용으로 전환되었습니다.';
}

function ReadOnlyCollabState({
  content,
  reason,
  resolveFileUrl,
}: {
  content: BlockContent;
  reason: 'relay_unavailable' | 'permission_revoked' | null;
  resolveFileUrl?: (url: string) => Promise<string>;
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-600 dark:text-amber-300">
        {resolveReadOnlyMessage(reason)}
      </div>
      <BlockViewer content={content} resolveFileUrl={resolveFileUrl} />
    </div>
  );
}

function CollaborativeBlockEditorInner({
  session,
  authToken,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
  onChange,
}: {
  session: CollaborativeSession;
  authToken: string;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  onChange?: (content: BlockContent) => void;
}) {
  const theme = useResolvedTheme();
  const disposeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onChangeRef = useRef(onChange);
  const [readOnlyReason, setReadOnlyReason] = useState<'relay_unavailable' | 'permission_revoked' | null>(null);
  const [fallbackContent, setFallbackContent] = useState<BlockContent>(() => session.snapshotContent ?? []);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const ydoc = useMemo(() => {
    if (session.yjsState) {
      const doc = new Y.Doc();
      Y.applyUpdate(doc, decodeBase64ToUint8Array(session.yjsState));
      return doc;
    }
    if (session.snapshotContent?.length) {
      const codecEditor = BlockNoteEditor.create({ schema: fullSchema });
      return blocksToYDoc(codecEditor, session.snapshotContent as never);
    }
    return new Y.Doc();
  }, [session.snapshotContent, session.yjsState, session.roomKey]);

  const provider = useMemo(() => {
    return new WebsocketProvider(
      toWebSocketUrl(session.wsPath),
      session.roomKey,
      ydoc,
      {
        maxBackoffTime: 4000,
        params: { token: authToken },
      },
    );
  }, [authToken, session.roomKey, session.wsPath, ydoc]);

  const editor = useCreateBlockNote({
    schema: fullSchema,
    ...(placeholder ? { placeholders: { default: placeholder } } : {}),
    collaboration: {
      fragment: ydoc.getXmlFragment('prosemirror'),
      user: {
        name: session.user.fullName,
        color: colorForUser(session.user.id),
      },
      provider,
      showCursorLabels: 'activity',
    },
    uploadFile,
    resolveFileUrl,
  });

  useEffect(() => {
    const handleConnectionClose = (event: CloseEvent | null) => {
      if (!event) {
        return;
      }
      if (event.code === 4403) {
        setReadOnlyReason('permission_revoked');
        provider.disconnect();
        return;
      }
      if (event.code === 1011 || event.code === 1013) {
        setReadOnlyReason('relay_unavailable');
        provider.disconnect();
      }
    };

    provider.on('connection-close', handleConnectionClose);
    return () => {
      provider.off('connection-close', handleConnectionClose);
    };
  }, [provider]);

  useEffect(() => {
    if (disposeTimerRef.current) {
      clearTimeout(disposeTimerRef.current);
      disposeTimerRef.current = null;
    }
    provider.connect();

    return () => {
      disposeTimerRef.current = setTimeout(() => {
        provider.disconnect();
        (provider as { destroy?: () => void }).destroy?.();
        ydoc.destroy();
      }, 0);
    };
  }, [provider, ydoc]);

  useEffect(() => {
    const unsubscribe = editor.onChange(() => {
      const content = editor.document as unknown as BlockContent;
      setFallbackContent(content);
      onChangeRef.current?.(content);
    });

    return () => {
      unsubscribe();
    };
  }, [editor]);

  if (readOnlyReason) {
    return (
      <ReadOnlyCollabState
        content={fallbackContent}
        reason={readOnlyReason}
        resolveFileUrl={resolveFileUrl}
      />
    );
  }

  return (
    <div className={`[&_.bn-container]:!bg-transparent [&_.bn-editor]:!bg-transparent ${className ?? ''}`}>
      <MantineProvider forceColorScheme={theme}>
        <BlockNoteView
          editor={editor}
          editable
          theme={theme}
        />
      </MantineProvider>
    </div>
  );
}

export function CollaborativeBlockEditor({
  sessionKey,
  authToken,
  loadSession,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
  onChange,
}: CollaborativeBlockEditorProps) {
  const [session, setSession] = useState<CollaborativeSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadSessionRef = useRef(loadSession);

  useEffect(() => {
    loadSessionRef.current = loadSession;
  }, [loadSession]);

  useEffect(() => {
    let cancelled = false;
    setSession(null);
    setError(null);
    void loadSessionRef.current()
      .then((value) => {
        if (!cancelled) {
          setSession(value);
        }
      })
      .catch((caughtError) => {
        if (!cancelled) {
          setError(caughtError instanceof Error ? caughtError.message : '협업 세션을 시작하지 못했습니다.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sessionKey]);

  if (error) {
    return (
      <div className="rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-sm text-[var(--ui-color-danger)]">
        {error}
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex items-center gap-2 px-1 py-2 text-sm text-[var(--ui-color-ink-subtle)]">
        <Loader2 size={16} className="animate-spin" />
        <span>실시간 협업 세션을 준비하는 중입니다.</span>
      </div>
    );
  }

  if (session.realtimeStatus !== 'enabled') {
    return (
      <ReadOnlyCollabState
        content={session.snapshotContent ?? []}
        reason={session.readOnlyReason}
        resolveFileUrl={resolveFileUrl}
      />
    );
  }

  return (
    <CollaborativeBlockEditorInner
      key={sessionKey}
      session={session}
      authToken={authToken}
      placeholder={placeholder}
      className={className}
      uploadFile={uploadFile}
      resolveFileUrl={resolveFileUrl}
      onChange={onChange}
    />
  );
}
