import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { MantineProvider } from '@mantine/core';
import { BlockNoteEditor } from '@blocknote/core';
import { blocksToYDoc, withCollaboration } from '@blocknote/core/yjs';
import { BlockNoteView } from '@blocknote/mantine';
import { useCreateBlockNote } from '@blocknote/react';
import { Loader2 } from 'lucide-react';
import * as Y from 'yjs';
import '@mantine/core/styles.css';
import '@blocknote/core/fonts/inter.css';
import '@blocknote/mantine/style.css';

import { BlockViewer } from './block-viewer';
import { createAuthenticatedCollabProvider } from './authenticated-collab-provider';
import {
  normalizeBlockNoteCopyPlainText,
  preferRichTextPaste,
} from './clipboard';
import { fullSchema } from './schema';
import { useResolvedTheme } from './use-theme';
import type { BlockContent } from './types';
import {
  collaborativeSessionReducer,
  colorForCollaborativeUser,
  COLLAB_CLOSE_CODE_TOO_MANY_CONNECTIONS,
  INITIAL_COLLABORATIVE_SESSION_STATE,
  resolveCollaborativeReadOnlyMessage,
  toCollaborativeWebSocketUrl,
  type CollaborativeBlockEditorMessages,
  type CollaborativeReadOnlyReason,
  type CollaborativeSession,
} from './collaborative-session';

export interface CollaborativeBlockEditorProps {
  sessionKey: string;
  authToken: string;
  loadSession: () => Promise<CollaborativeSession>;
  messages: CollaborativeBlockEditorMessages;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  contentOverride?: BlockContent | null;
  contentOverrideVersion?: number;
  onChange?: (
    content: BlockContent,
    metadata: CollaborativeBlockEditorChangeMetadata,
  ) => void;
}

interface CollaborativeBlockEditorChangeMetadata {
  yjsState: string;
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
  for (let index = 0; index < value.length; index += 1) {
    binary += String.fromCharCode(value[index]);
  }
  return window.btoa(binary);
}

function ReadOnlyCollabState({
  content,
  reason,
  messages,
  resolveFileUrl,
}: {
  content: BlockContent;
  reason: CollaborativeReadOnlyReason;
  messages: CollaborativeBlockEditorMessages;
  resolveFileUrl?: (url: string) => Promise<string>;
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-ui-warning/30 bg-ui-warning/10 px-3 py-2 text-[length:var(--ui-text-body)] text-ui-warning">
        {resolveCollaborativeReadOnlyMessage(reason, messages)}
      </div>
      <BlockViewer content={content} resolveFileUrl={resolveFileUrl} />
    </div>
  );
}

function CollaborativeBlockEditorInner({
  session,
  authToken,
  messages,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
  contentOverride,
  contentOverrideVersion,
  onChange,
}: {
  session: CollaborativeSession;
  authToken: string;
  messages: CollaborativeBlockEditorMessages;
  placeholder?: string;
  className?: string;
  uploadFile?: (file: File) => Promise<string>;
  resolveFileUrl?: (url: string) => Promise<string>;
  contentOverride?: BlockContent | null;
  contentOverrideVersion?: number;
  onChange?: (
    content: BlockContent,
    metadata: CollaborativeBlockEditorChangeMetadata,
  ) => void;
}) {
  const theme = useResolvedTheme();
  const appliedContentOverrideVersionRef = useRef<number | null>(null);
  const onChangeRef = useRef(onChange);
  const [readOnlyReason, setReadOnlyReason] = useState<
    'relay_unavailable' | 'permission_revoked' | 'too_many_connections' | null
  >(null);
  const [fallbackContent, setFallbackContent] = useState<BlockContent>(
    () => session.snapshotContent ?? [],
  );

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
      try {
        return blocksToYDoc(codecEditor, session.snapshotContent as never);
      } finally {
        codecEditor._tiptapEditor.destroy();
      }
    }
    return new Y.Doc();
  }, [session.snapshotContent, session.yjsState]);

  const provider = useMemo(() => {
    return createAuthenticatedCollabProvider({
      url: toCollaborativeWebSocketUrl(session.wsPath, window.location.origin),
      roomKey: session.roomKey,
      doc: ydoc,
      token: authToken,
    });
  }, [authToken, session.roomKey, session.wsPath, ydoc]);

  const editor = useCreateBlockNote(
    withCollaboration({
      schema: fullSchema,
      ...(placeholder ? { placeholders: { default: placeholder } } : {}),
      collaboration: {
        fragment: ydoc.getXmlFragment('prosemirror'),
        user: {
          name: session.user.fullName,
          color: colorForCollaborativeUser(session.user.id),
        },
        provider,
        showCursorLabels: 'activity',
      },
      uploadFile,
      resolveFileUrl,
      pasteHandler: preferRichTextPaste,
    }),
  );

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
      if (event.code === COLLAB_CLOSE_CODE_TOO_MANY_CONNECTIONS) {
        setReadOnlyReason('too_many_connections');
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
    provider.connect();

    return () => {
      provider.disconnect();
      (provider as { destroy?: () => void }).destroy?.();
      ydoc.destroy();
    };
  }, [provider, ydoc]);

  useEffect(() => {
    const unsubscribe = editor.onChange(() => {
      const content = editor.document as unknown as BlockContent;
      const yjsState = encodeUint8ArrayToBase64(Y.encodeStateAsUpdate(ydoc));
      setFallbackContent(content);
      onChangeRef.current?.(content, { yjsState });
    });

    return () => {
      unsubscribe();
    };
  }, [editor, ydoc]);

  useEffect(() => {
    if (
      !contentOverrideVersion ||
      appliedContentOverrideVersionRef.current === contentOverrideVersion ||
      !contentOverride
    ) {
      return;
    }
    appliedContentOverrideVersionRef.current = contentOverrideVersion;
    editor.replaceBlocks(
      editor.document.map((block) => block.id),
      contentOverride as never,
    );
  }, [contentOverride, contentOverrideVersion, editor]);

  if (readOnlyReason) {
    return (
      <ReadOnlyCollabState
        content={fallbackContent}
        reason={readOnlyReason}
        messages={messages}
        resolveFileUrl={resolveFileUrl}
      />
    );
  }

  return (
    <div
      className={`ui-block-editor [&_.bn-root]:!bg-transparent [&_.bn-container]:!bg-transparent [&_.bn-editor]:!bg-transparent ${className ?? ''}`}
    >
      <MantineProvider forceColorScheme={theme}>
        <BlockNoteView
          editor={editor}
          editable
          onCopy={(event) => normalizeBlockNoteCopyPlainText(event)}
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
  messages,
  placeholder,
  className,
  uploadFile,
  resolveFileUrl,
  contentOverride,
  contentOverrideVersion,
  onChange,
}: CollaborativeBlockEditorProps) {
  const [{ session, error }, dispatchSession] = useReducer(
    collaborativeSessionReducer,
    INITIAL_COLLABORATIVE_SESSION_STATE,
  );
  const loadSessionRef = useRef(loadSession);

  useEffect(() => {
    loadSessionRef.current = loadSession;
  }, [loadSession]);

  useEffect(() => {
    let cancelled = false;
    dispatchSession({ type: 'loading' });
    void loadSessionRef
      .current()
      .then((value) => {
        if (!cancelled) {
          dispatchSession({
            type: 'ready',
            session: value,
          });
        }
      })
      .catch((caughtError) => {
        if (!cancelled) {
          dispatchSession({
            type: 'failed',
            error:
              caughtError instanceof Error
                ? caughtError.message
                : messages.startFailed,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [messages.startFailed, sessionKey]);

  if (error) {
    return (
      <div className="rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[length:var(--ui-text-body)] text-[var(--ui-color-danger)]">
        {error}
      </div>
    );
  }

  if (!session) {
    return (
      <div className="flex items-center gap-2 px-1 py-2 text-[length:var(--ui-text-body)] text-[var(--ui-color-ink-subtle)]">
        <Loader2 size={16} className="animate-spin" />
        <span>{messages.preparing}</span>
      </div>
    );
  }

  if (session.realtimeStatus !== 'enabled') {
    return (
      <ReadOnlyCollabState
        content={session.snapshotContent ?? []}
        reason={session.readOnlyReason}
        messages={messages}
        resolveFileUrl={resolveFileUrl}
      />
    );
  }

  return (
    <CollaborativeBlockEditorInner
      key={sessionKey}
      session={session}
      authToken={authToken}
      messages={messages}
      placeholder={placeholder}
      className={className}
      uploadFile={uploadFile}
      resolveFileUrl={resolveFileUrl}
      contentOverride={contentOverride}
      contentOverrideVersion={contentOverrideVersion}
      onChange={onChange}
    />
  );
}
