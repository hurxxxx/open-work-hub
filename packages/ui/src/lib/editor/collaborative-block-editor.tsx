import { useEffect, useMemo, useRef, useState } from 'react';
import { MantineProvider } from '@mantine/core';
import { BlockNoteView } from '@blocknote/mantine';
import { useCreateBlockNote } from '@blocknote/react';
import { Loader2 } from 'lucide-react';
import { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';

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
  snapshotContent: BlockContent | null;
  yjsState: string | null;
};

type SnapshotPayload = {
  content: BlockContent;
  yjsState: string;
};

export interface CollaborativeBlockEditorProps {
  sessionKey: string;
  authToken: string;
  loadSession: () => Promise<CollaborativeSession>;
  saveSnapshot: (payload: SnapshotPayload) => Promise<{ updatedAt?: string | null } | void>;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  onPersisted?: (payload: { content: BlockContent; updatedAt?: string | null }) => void;
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

function encodeUint8ArrayToBase64(value: Uint8Array): string {
  let binary = '';
  for (const byte of value) {
    binary += String.fromCharCode(byte);
  }
  return window.btoa(binary);
}

function toWebSocketUrl(wsPath: string): string {
  const resolved = new URL(wsPath, window.location.origin);
  resolved.protocol = resolved.protocol === 'https:' ? 'wss:' : 'ws:';
  return resolved.toString();
}

function CollaborativeBlockEditorInner({
  session,
  authToken,
  saveSnapshot,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
  onPersisted,
}: {
  session: CollaborativeSession;
  authToken: string;
  saveSnapshot: (payload: SnapshotPayload) => Promise<{ updatedAt?: string | null } | void>;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  onPersisted?: (payload: { content: BlockContent; updatedAt?: string | null }) => void;
}) {
  const theme = useResolvedTheme();
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disposeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveSnapshotRef = useRef(saveSnapshot);
  const onPersistedRef = useRef(onPersisted);

  useEffect(() => {
    saveSnapshotRef.current = saveSnapshot;
    onPersistedRef.current = onPersisted;
  }, [onPersisted, saveSnapshot]);

  const ydoc = useMemo(() => {
    const doc = new Y.Doc();
    if (session.yjsState) {
      Y.applyUpdate(doc, decodeBase64ToUint8Array(session.yjsState));
    }
    return doc;
  }, [session.yjsState, session.roomKey]);

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
    ...(session.yjsState
      ? {}
      : {
          initialContent: session.snapshotContent?.length
            ? session.snapshotContent as never
            : undefined,
        }),
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
    async function persistSnapshot() {
      const content = editor.document as unknown as BlockContent;
      const yjsState = encodeUint8ArrayToBase64(Y.encodeStateAsUpdate(ydoc));
      const response = await saveSnapshotRef.current({ content, yjsState });
      onPersistedRef.current?.({ content, updatedAt: response?.updatedAt ?? null });
    }

    const unsubscribe = editor.onChange(() => {
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
      }
      persistTimerRef.current = setTimeout(() => {
        void persistSnapshot();
      }, 2000);
    });

    return () => {
      unsubscribe();
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
      }
      void persistSnapshot();
    };
  }, [editor, ydoc]);

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
  saveSnapshot,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
  onPersisted,
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

  return (
    <CollaborativeBlockEditorInner
      key={sessionKey}
      session={session}
      authToken={authToken}
      saveSnapshot={saveSnapshot}
      placeholder={placeholder}
      className={className}
      uploadFile={uploadFile}
      resolveFileUrl={resolveFileUrl}
      onPersisted={onPersisted}
    />
  );
}
