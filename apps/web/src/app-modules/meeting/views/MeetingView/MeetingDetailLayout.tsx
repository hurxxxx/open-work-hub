// Two-pane meeting workspace: collaborative notes editor on the left + the
// MeetingDetail sidebar on the right. Extracted from MeetingDetailView so
// the same layout can be hosted in:
//   - the dedicated workspace-scoped meeting detail route
//   - an embedded modal (the calendar's MeetingPreviewModal)
//
// Loads + ensures meeting notes, manages title editing, threads onChanged /
// onDeleted callbacks back to the host so it can refetch its own data.
import { useAppAdmission } from '@/src/platform/apps/app-bootstrap-context';
import { isParticipant } from '../../api/meeting-permissions';
import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import {
  BlockViewer,
  Button,
  CollaborativeBlockEditor,
  DetailDrawer,
  InlineNotice,
} from '@open-work-hub/ui';
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  PanelRightOpen,
  Pencil,
  X,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState,
  useSyncExternalStore,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import {
  getDocsCollabSession,
  getDocsItem,
  listDocPages,
  makeDocsPageRef,
  mediaResourceTypeForDocsPage,
  recordDocView,
  updateDocPage,
} from '@/src/app-modules/docs/public-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  ensureMeetingNotes,
  getMeeting,
  type MeetingDetail as MeetingDetailType,
} from '../../api/meeting-api';

import { MeetingDetail } from './MeetingDetail';
import {
  MEETING_DETAIL_INITIAL_STATE,
  formatMeetingDetailRange,
  meetingDetailReducer,
} from './meeting-detail-layout-model';

export interface MeetingDetailLayoutProps {
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

function getMediaQuerySnapshot(query: string): boolean {
  return typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function'
    ? window.matchMedia(query).matches
    : false;
}

function getServerMediaQuerySnapshot(): boolean {
  return false;
}

function subscribeMediaQuery(
  query: string,
  onStoreChange: () => void,
): () => void {
  if (
    typeof window === 'undefined' ||
    typeof window.matchMedia !== 'function'
  ) {
    return () => undefined;
  }

  const mediaQuery = window.matchMedia(query);
  mediaQuery.addEventListener('change', onStoreChange);

  return () => {
    mediaQuery.removeEventListener('change', onStoreChange);
  };
}

function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    useCallback(
      (onStoreChange) => subscribeMediaQuery(query, onStoreChange),
      [query],
    ),
    useCallback(() => getMediaQuerySnapshot(query), [query]),
    getServerMediaQuerySnapshot,
  );
}

export function MeetingDetailLayout(props: MeetingDetailLayoutProps) {
  const { token } = useAuth();
  return (
    <MeetingDetailLayoutContent
      key={[token, props.meetingId].join(':')}
      {...props}
    />
  );
}
function MeetingDetailLayoutContent(props: MeetingDetailLayoutProps) {
  return useMeetingDetailLayoutElement(props);
}

function useMeetingDetailLayoutElement({
  meetingId,
  onChanged,
  onDeleted,
  onClose,
  backHref,
}: MeetingDetailLayoutProps) {
  const { t, i18n } = useTranslation('apps');
  const { token, user } = useAuth();
  const canReadDocs = useAppAdmission('docs');
  const timeZone = normalizeTimeZone(user?.time_zone);
  const { uploadFile, createLinkedUploadFile, resolveFileUrl } =
    useMediaUpload();

  const [state, dispatch] = useReducer(
    meetingDetailReducer,
    MEETING_DETAIL_INITIAL_STATE,
  );
  const { meeting, notesDoc, notesPage, loading, error, detailOpen } = state;
  const detailPanelDocked = useMediaQuery('(min-width: 1280px)');

  const meetingsRoot = backHref ?? buildAppHref({ routeId: 'meeting.root' });
  const notesDocId = notesDoc?.id ?? null;
  const notesPageId = notesPage?.id ?? null;
  const [collabEditingNotesPageId, setCollabEditingNotesPageId] = useState<
    string | null
  >(null);

  const loadWorkspace = useCallback(async () => {
    if (!token) {
      dispatch({
        type: 'loadFailed',
        error: t('meeting.workspace.loadFailed'),
      });
      return;
    }
    const resolvedToken = token;
    const resolvedMeetingId = meetingId;
    dispatch({ type: 'loadStarted' });
    try {
      let detail = await getMeeting(resolvedToken, resolvedMeetingId);
      if (
        !canReadDocs ||
        ((!detail.notes_doc_id || !detail.notes_page_id) &&
          !isParticipant(user, detail))
      ) {
        dispatch({
          type: 'loadSucceeded',
          meeting: detail,
          notesDoc: null,
          notesPage: null,
        });
        return;
      }
      if (!detail.notes_doc_id || !detail.notes_page_id) {
        detail = await ensureMeetingNotes(resolvedToken, resolvedMeetingId);
      }

      async function loadNotesFor(current: MeetingDetailType) {
        const innerNotesDocId = current.notes_doc_id;
        const innerNotesPageId = current.notes_page_id;
        if (!innerNotesDocId || !innerNotesPageId) {
          throw new Error(t('meeting.workspace.notesPrepareFailed'));
        }
        const [doc, pages] = await Promise.all([
          getDocsItem(resolvedToken, innerNotesDocId, null),
          listDocPages(resolvedToken, innerNotesDocId, null),
        ]);
        const page =
          pages.items.find(
            (item) =>
              item.id === innerNotesPageId ||
              item.source_page_id === innerNotesPageId,
          ) ?? null;
        return { doc, page };
      }

      let { doc, page } = await loadNotesFor(detail);
      if (!page && !isParticipant(user, detail)) {
        dispatch({
          type: 'loadSucceeded',
          meeting: detail,
          notesDoc: doc,
          notesPage: null,
        });
        return;
      }
      if (!page) {
        detail = await ensureMeetingNotes(resolvedToken, resolvedMeetingId);
        ({ doc, page } = await loadNotesFor(detail));
      }
      if (!page) {
        throw new Error(t('meeting.workspace.notesPageFailed'));
      }

      dispatch({
        type: 'loadSucceeded',
        meeting: detail,
        notesDoc: doc,
        notesPage: page,
      });
    } catch (err) {
      dispatch({
        type: 'loadFailed',
        error:
          err instanceof Error
            ? err.message
            : t('meeting.workspace.loadFailed'),
      });
    }
  }, [canReadDocs, meetingId, t, token, user]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (!token || !notesDocId || !notesPageId) {
      return;
    }
    void recordDocView(token, notesDocId, notesPageId, null);
  }, [notesDocId, notesPageId, token]);

  useEffect(() => {
    setCollabEditingNotesPageId(null);
  }, [notesPageId]);

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
        );
        dispatch({ type: 'setNotesPage', notesPage: updated });
      } catch {
        // Keep the existing title when save fails.
      }
    },
    [notesPage, token],
  );

  const notesUploadFile = useMemo(
    () =>
      createLinkedUploadFile?.(
        notesPage?.source_page_id
          ? {
              resourceType: mediaResourceTypeForDocsPage(),
              resourceId: notesPage.source_page_id,
            }
          : null,
      ) ?? uploadFile,
    [createLinkedUploadFile, notesPage?.source_page_id, uploadFile],
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
            {t('common:actions.close')}
          </Button>
        ) : (
          <Link
            to={meetingsRoot}
            className="app-text-control-sm rounded-md border border-app-border px-3 py-2 text-app-ink hover:bg-app-surface-hover"
          >
            {t('meeting.workspace.backToMeetings')}
          </Link>
        )}
      </div>
    );
  }

  if (!meeting) return null;
  if (!notesPage) {
    return (
      <div className="flex h-full min-h-0 flex-col overflow-auto">
        <p className="app-text-caption px-4 py-2 text-app-ink/60">
          {t('meeting.companyContentNotice')}
        </p>
        <p role="status" className="app-text-body px-4 py-2 text-app-ink/60">
          {t('meeting.notesUnavailable')}
        </p>
        <MeetingDetail
          meetingId={meetingId}
          onChanged={() => {
            void loadWorkspace();
            onChanged?.();
          }}
          onDeleted={() => onDeleted?.()}
          onClose={onClose}
          showCloseButton={Boolean(onClose)}
        />
      </div>
    );
  }

  const notesDocPath = meeting.notes_doc_id
    ? buildAppHref({
        routeId: 'docs.document',
        pathParams: { docId: meeting.notes_doc_id },
      })
    : null;
  const editorAuthToken = token;
  const canEditNotes = Boolean(
    editorAuthToken && notesDoc?.can_edit && notesPage.can_edit,
  );

  const handleChanged = () => {
    void loadWorkspace();
    onChanged?.();
  };

  return (
    <div className="flex h-full min-w-0 bg-app-bg">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-app-border bg-app-surface px-4 py-3 sm:px-6 sm:py-4">
          <div className="flex items-start justify-between gap-3 sm:items-center sm:gap-4">
            <div className="min-w-0">
              {onClose ? (
                <button
                  type="button"
                  onClick={onClose}
                  className="app-text-caption inline-flex items-center gap-1 text-app-ink/50 hover:text-app-accent"
                >
                  <X size={14} />
                  {t('common:actions.close')}
                </button>
              ) : (
                <Link
                  to={meetingsRoot}
                  className="app-text-caption inline-flex items-center gap-1 text-app-ink/50 hover:text-app-accent"
                >
                  <ArrowLeft size={14} />
                  {t('meeting.meetings')}
                </Link>
              )}
              <h1 className="app-text-title-md mt-2 truncate text-app-ink">
                {meeting.title}
              </h1>
              <p className="app-text-caption mt-1 text-app-ink/60 dark:text-app-ink/70">
                {formatMeetingDetailRange(
                  meeting.start_at,
                  meeting.end_at,
                  timeZone,
                  i18n.language,
                )}{' '}
                · {meeting.organizer_name}
              </p>
              <p className="app-text-caption mt-1 text-app-ink/60">
                {t('meeting.companyContentNotice')}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {!detailPanelDocked ? (
                <button
                  aria-label={t('meeting.workspace.openDetails')}
                  className="app-text-control-sm inline-flex h-9 items-center gap-1 rounded-md border border-app-border px-3 text-app-ink transition-colors hover:bg-app-surface-hover"
                  onClick={() =>
                    dispatch({ type: 'setDetailOpen', open: true })
                  }
                  type="button"
                >
                  <PanelRightOpen size={14} />
                  <span className="hidden sm:inline">
                    {t('meeting.workspace.detail')}
                  </span>
                </button>
              ) : null}
              {notesDocPath ? (
                <Link
                  aria-label={t('meeting.workspace.openInDocs')}
                  to={notesDocPath}
                  target={onClose ? '_blank' : undefined}
                  rel={onClose ? 'noopener noreferrer' : undefined}
                  className="app-text-control-sm inline-flex h-9 items-center gap-1 rounded-md border border-app-border px-3 text-app-ink transition-colors hover:bg-app-surface-hover"
                >
                  <span className="hidden sm:inline">
                    {t('meeting.workspace.openInDocsShort')}
                  </span>
                  <ExternalLink size={13} />
                </Link>
              ) : null}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-white dark:bg-app-surface">
          <div className="mx-auto w-full max-w-4xl px-4 py-8 sm:px-6 lg:px-10 lg:py-12">
            {error ? (
              <InlineNotice
                role="alert"
                className="mb-6 app-text-body"
                tone="danger"
              >
                {error}
              </InlineNotice>
            ) : null}

            <div className="space-y-6">
              <div className="space-y-4">
                {canEditNotes ? (
                  <input
                    aria-label={t('meeting.workspace.notesPlaceholder')}
                    key={notesPage.id}
                    type="text"
                    defaultValue={notesPage.title}
                    placeholder={t('meeting.workspace.notesPlaceholder')}
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
                  <h2 className="app-text-title-xl text-app-ink">
                    {notesPage.title}
                  </h2>
                )}
                <p className="app-text-caption text-app-ink/50">
                  {t('meeting.workspace.notesSync')}
                </p>
              </div>

              <div className="prose max-w-none dark:prose-invert">
                {canEditNotes &&
                editorAuthToken &&
                collabEditingNotesPageId === notesPage.id ? (
                  <CollaborativeBlockEditor
                    sessionKey={notesPage.id}
                    authToken={editorAuthToken}
                    loadSession={async () => {
                      const session = await getDocsCollabSession(
                        editorAuthToken,
                        makeDocsPageRef(
                          notesPage.source_type,
                          notesPage.source_page_id,
                        ),
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
                        snapshotContent: (session.snapshot_content_blocks ??
                          []) as never,
                        yjsState: session.yjs_state,
                      };
                    }}
                    messages={{
                      permissionRevoked: t('docs.collab.permissionRevoked'),
                      relayUnavailable: t('docs.collab.relayUnavailable'),
                      startFailed: t('docs.collab.startFailed'),
                      preparing: t('docs.collab.preparing'),
                      tooManyConnections: t('docs.collab.tooManyConnections'),
                    }}
                    placeholder={t('meeting.workspace.editorPlaceholder')}
                    uploadFile={notesUploadFile}
                    resolveFileUrl={resolveFileUrl}
                    onChange={(content) => {
                      dispatch({
                        type: 'updateNotesContent',
                        content: content as Record<string, unknown>[],
                      });
                    }}
                  />
                ) : canEditNotes && editorAuthToken ? (
                  <div className="space-y-3">
                    <div className="flex justify-end">
                      <Button
                        type="button"
                        size="dense"
                        variant="primary"
                        onClick={() =>
                          setCollabEditingNotesPageId(notesPage.id)
                        }
                      >
                        <Pencil size={14} />
                        {t('docs.startEditing')}
                      </Button>
                    </div>
                    <BlockViewer
                      key={notesPage.id}
                      content={(notesPage.content_blocks as never) ?? []}
                      resolveFileUrl={resolveFileUrl}
                    />
                  </div>
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

      {detailPanelDocked ? (
        <aside className="w-[420px] shrink-0 border-l border-app-border bg-app-surface">
          <MeetingDetail
            meetingId={meetingId}
            onChanged={handleChanged}
            onDeleted={() => {
              onDeleted?.();
            }}
            showCloseButton={false}
          />
        </aside>
      ) : null}

      <DetailDrawer
        contentClassName="border-app-border bg-app-surface"
        description={t('meeting.workspace.detailDrawerDescription')}
        embedded
        onOpenChange={(open) => dispatch({ type: 'setDetailOpen', open })}
        open={detailOpen && !detailPanelDocked}
        title={t('meeting.workspace.detailDrawerTitle')}
      >
        <MeetingDetail
          meetingId={meetingId}
          onClose={() => dispatch({ type: 'setDetailOpen', open: false })}
          onChanged={handleChanged}
          onDeleted={() => {
            dispatch({ type: 'setDetailOpen', open: false });
            onDeleted?.();
          }}
          showCloseButton
        />
      </DetailDrawer>
    </div>
  );
}
