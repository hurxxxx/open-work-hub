// Two-pane meeting workspace: collaborative notes editor on the left + the
// MeetingDetail sidebar on the right. Extracted from MeetingWorkspaceView so
// the same layout can be hosted in:
//   - the dedicated meeting page route (/w/{slug}/meeting/{meetingId})
//   - an embedded modal (the calendar's MeetingPreviewModal)
//
// Loads + ensures meeting notes, manages title editing, threads onChanged /
// onDeleted callbacks back to the host so it can refetch its own data.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Loader2, X } from 'lucide-react';
import { BlockViewer, Button, CollaborativeBlockEditor } from '@aidoo/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getDocsCollabSession,
  getDocsItem,
  listDocPages,
  makeDocsPageRef,
  mediaResourceTypeForDocsPage,
  recordDocView,
  updateDocPage,
  type DocsHubItem,
  type DocsPageItem,
} from '@/src/app-modules/docs/public-api';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import {
  ensureMeetingNotes,
  getMeeting,
  parseServerDateTime,
  type MeetingDetail as MeetingDetailType,
} from '../../api/meeting-api';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

import { MeetingDetail } from './MeetingDetail';

export interface MeetingWorkspaceLayoutProps {
  workspaceSlug: string;
  meetingId: string;
  /**
   * Called after the meeting (or its notes) is changed by the user inside the
   * layout. Hosts use this to refetch their own list/calendar data.
   */
  onChanged?: () => void;
  /**
   * Called after the meeting is deleted. Hosts typically navigate away or
   * close the modal here.
   */
  onDeleted?: () => void;
  /**
   * Called when the user clicks the explicit close affordance. When provided,
   * a close button is rendered in the header instead of the back link.
   */
  onClose?: () => void;
  /**
   * Where the back-arrow link points when no ``onClose`` is provided.
   * Defaults to the meetings root for the current workspace.
   */
  backHref?: string;
}

function formatRange(start: string, end: string): string {
  const s = parseServerDateTime(start);
  const e = parseServerDateTime(end);
  return `${s.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })} - ${e.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}`;
}

export function MeetingWorkspaceLayout({
  workspaceSlug,
  meetingId,
  onChanged,
  onDeleted,
  onClose,
  backHref,
}: MeetingWorkspaceLayoutProps) {
  const { token } = useAuth();
  const { uploadFile, createLinkedUploadFile, resolveFileUrl } = useMediaUpload();

  const [meeting, setMeeting] = useState<MeetingDetailType | null>(null);
  const [notesDoc, setNotesDoc] = useState<DocsHubItem | null>(null);
  const [notesPage, setNotesPage] = useState<DocsPageItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const meetingsRoot = backHref ?? buildWorkspaceAppPath(workspaceSlug, 'meeting');
  const notesDocId = notesDoc?.id ?? null;
  const notesPageId = notesPage?.id ?? null;

  const loadWorkspace = useCallback(async () => {
    if (!token) return;
    const resolvedToken = token;
    const resolvedWorkspaceSlug = workspaceSlug;
    const resolvedMeetingId = meetingId;
    setLoading(true);
    setError(null);
    try {
      let detail = await getMeeting(resolvedToken, resolvedWorkspaceSlug, resolvedMeetingId);
      if (!detail.notes_doc_id || !detail.notes_page_id) {
        detail = await ensureMeetingNotes(resolvedToken, resolvedWorkspaceSlug, resolvedMeetingId);
      }

      async function loadNotesFor(current: MeetingDetailType) {
        const innerNotesDocId = current.notes_doc_id;
        const innerNotesPageId = current.notes_page_id;
        if (!innerNotesDocId || !innerNotesPageId) {
          throw new Error('회의 메모를 준비할 수 없습니다.');
        }
        const [doc, pages] = await Promise.all([
          getDocsItem(resolvedToken, innerNotesDocId, null, resolvedWorkspaceSlug),
          listDocPages(resolvedToken, innerNotesDocId, null, resolvedWorkspaceSlug),
        ]);
        const page = pages.items.find(
          (item) => item.id === innerNotesPageId || item.source_page_id === innerNotesPageId,
        ) ?? null;
        return { doc, page };
      }

      let { doc, page } = await loadNotesFor(detail);
      if (!page) {
        detail = await ensureMeetingNotes(resolvedToken, resolvedWorkspaceSlug, resolvedMeetingId);
        ({ doc, page } = await loadNotesFor(detail));
      }
      if (!page) {
        throw new Error('회의 메모 페이지를 불러올 수 없습니다.');
      }

      setMeeting(detail);
      setNotesDoc(doc);
      setNotesPage(page);
    } catch (err) {
      setError(err instanceof Error ? err.message : '회의 workspace를 불러올 수 없습니다.');
      setMeeting(null);
      setNotesDoc(null);
      setNotesPage(null);
    } finally {
      setLoading(false);
    }
  }, [meetingId, token, workspaceSlug]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (!token || !notesDocId || !notesPageId || !workspaceSlug) {
      return;
    }
    void recordDocView(token, notesDocId, notesPageId, null, workspaceSlug);
  }, [notesDocId, notesPageId, token, workspaceSlug]);

  const handleTitleSave = useCallback(
    async (nextTitle: string) => {
      if (!token || !notesPage) return;
      const trimmed = nextTitle.trim();
      if (!trimmed || trimmed === notesPage.title) return;
      try {
        const updated = await updateDocPage(
          token,
          notesPage.id,
          { title: trimmed },
          null,
          workspaceSlug,
        );
        setNotesPage(updated);
      } catch {
        // Keep the existing title when save fails.
      }
    },
    [notesPage, token, workspaceSlug],
  );

  const notesUploadFile = useMemo(
    () =>
      createLinkedUploadFile?.(
        notesPage?.source_page_id
          ? {
              resourceType: mediaResourceTypeForDocsPage(notesPage.source_type),
              resourceId: notesPage.source_page_id,
            }
          : null,
      ) ?? uploadFile,
    [createLinkedUploadFile, notesPage?.source_page_id, notesPage?.source_type, uploadFile],
  );

  if (loading && !meeting) {
    return (
      <div className="flex h-full items-center justify-center text-app-ink/40">
        <Loader2 size={18} className="animate-spin" />
      </div>
    );
  }

  if (error && !meeting) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="app-text-body text-app-ink/70">{error}</p>
        {onClose ? (
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
        ) : (
          <Link
            to={meetingsRoot}
            className="app-text-control-sm rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
          >
            회의 목록으로 돌아가기
          </Link>
        )}
      </div>
    );
  }

  if (!meeting || !notesPage) {
    return null;
  }

  const notesDocPath = meeting.notes_doc_id
    ? buildWorkspaceAppPath(workspaceSlug, 'docs', meeting.notes_doc_id)
    : null;
  const editorAuthToken = token;
  const canEditNotes = Boolean(editorAuthToken && notesDoc?.can_edit && notesPage.can_edit);

  const handleChanged = () => {
    void loadWorkspace();
    onChanged?.();
  };

  return (
    <div className="flex h-full min-w-0 bg-app-bg">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-app-border bg-app-surface px-6 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              {onClose ? (
                <button
                  type="button"
                  onClick={onClose}
                  className="app-text-caption inline-flex items-center gap-1 text-app-ink/50 hover:text-app-accent"
                >
                  <X size={14} />
                  닫기
                </button>
              ) : (
                <Link
                  to={meetingsRoot}
                  className="app-text-caption inline-flex items-center gap-1 text-app-ink/50 hover:text-app-accent"
                >
                  <ArrowLeft size={14} />
                  Meetings
                </Link>
              )}
              <h1 className="app-text-title-md mt-2 truncate text-app-ink">
                {meeting.title}
              </h1>
              <p className="app-text-caption mt-1 text-app-ink/60 dark:text-app-ink/70">
                {formatRange(meeting.start_at, meeting.end_at)} · {meeting.organizer_name}
              </p>
            </div>
            {notesDocPath ? (
              <Link
                to={notesDocPath}
                target={onClose ? '_blank' : undefined}
                rel={onClose ? 'noopener noreferrer' : undefined}
                className="app-text-control-sm inline-flex items-center gap-1 rounded-md border border-app-border px-3 py-2 text-app-ink transition-colors hover:bg-app-surface-hover"
              >
                Open in Docs
                <ExternalLink size={13} />
              </Link>
            ) : null}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-white dark:bg-[#1e1e24]">
          <div className="mx-auto w-full max-w-4xl px-10 py-12">
            {error ? (
              <div
                role="alert"
                className="app-text-body mb-6 rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
              >
                {error}
              </div>
            ) : null}

            <div className="space-y-6">
              <div className="space-y-4">
                {canEditNotes ? (
                  <input
                    key={notesPage.id}
                    type="text"
                    defaultValue={notesPage.title}
                    placeholder="회의 메모"
                    className="app-text-title-xl w-full bg-transparent text-app-ink placeholder:text-app-ink/30 focus:outline-none"
                    onBlur={(event) => void handleTitleSave(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        event.currentTarget.blur();
                      }
                      if (event.key === 'Escape') {
                        event.currentTarget.value = notesPage.title;
                        event.currentTarget.blur();
                      }
                    }}
                  />
                ) : (
                  <h2 className="app-text-title-xl text-app-ink">{notesPage.title}</h2>
                )}
                <p className="app-text-caption text-app-ink/50">
                  단일 notes page가 실시간으로 동기화됩니다.
                </p>
              </div>

              <div className="prose max-w-none dark:prose-invert">
                {canEditNotes && editorAuthToken ? (
                  <CollaborativeBlockEditor
                    sessionKey={`${workspaceSlug}:${notesPage.id}`}
                    authToken={editorAuthToken}
                    loadSession={async () => {
                      const session = await getDocsCollabSession(
                        editorAuthToken,
                        makeDocsPageRef(notesPage.source_type, notesPage.source_page_id),
                        workspaceSlug,
                      );
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
                    }}
                    placeholder="회의 메모를 작성하세요..."
                    uploadFile={notesUploadFile}
                    resolveFileUrl={resolveFileUrl}
                    onChange={(content) => {
                      setNotesPage((current) =>
                        current
                          ? {
                              ...current,
                              content_blocks: content as Record<string, unknown>[],
                            }
                          : current,
                      );
                    }}
                  />
                ) : (
                  <BlockViewer
                    key={notesPage.id}
                    content={(notesPage.content_blocks as never) ?? []}
                    resolveFileUrl={resolveFileUrl}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <aside className="w-[420px] shrink-0 border-l border-app-border bg-app-surface">
        <MeetingDetail
          workspaceSlug={workspaceSlug}
          meetingId={meetingId}
          onChanged={handleChanged}
          onDeleted={() => {
            onDeleted?.();
          }}
          showCloseButton={false}
        />
      </aside>
    </div>
  );
}
