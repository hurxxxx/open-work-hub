import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  Download,
  FileText,
  Loader2,
  MessageSquare,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';

import {
  ChatComposer,
  ChatThread,
  getConversation,
  listConversations,
  type ChatTurn,
  type ConversationDetail,
  type ConversationSummary,
  type ConversationTurn,
} from '@/src/app-modules/chatbot/public-api';
import { iterSseEvents } from '@/src/platform/api/sse-parser';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { cn } from '@/src/lib/utils';
import { MarkdownContent } from '@/src/components/artifacts/MarkdownContent';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import {
  type QnaAskResponse,
  type QnaDocument,
  type QnaDocumentDetail,
  type QnaStreamEvent,
  QnaApiError,
  deleteQnaDocument,
  downloadQnaFile,
  fetchQnaFileBlob,
  getQnaDocument,
  listQnaDocuments,
  listQnaNotices,
  streamQna,
  syncQnaBoard,
  uploadQnaDocument,
} from '../api/qna-api';
import { formatQnaBodyMarkdown } from './qna-body-markdown';

const UPLOAD_ACCEPT =
  '.pdf,.docx,.xlsx,.xls,.pptx,.ppt,.png,.jpg,.jpeg,.gif,.bmp,.tif,.tiff,.webp';

interface EvidenceItem {
  title: string;
  score?: number;
}

type PreviewKind = 'pdf' | 'image' | 'unsupported';

interface AttachmentPreviewState {
  documentId: string;
  filename: string;
  url: string;
  contentType: string;
  kind: PreviewKind;
}

function createId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

function buildConversationTitle(question: string): string {
  const compact = question.replace(/\s+/g, ' ').trim();
  if (compact.length <= 36) {
    return compact;
  }
  return `${compact.slice(0, 36)}...`;
}

function escapeMarkdown(value: string): string {
  return value.replace(/([`*_~])/g, '\\$1');
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) {
    return '';
  }
  return `${Math.round(score * 100)}%`;
}

function parseQnaStreamEvent(data: string): QnaStreamEvent | null {
  try {
    const parsed = JSON.parse(data) as Partial<QnaStreamEvent>;
    if (
      parsed.type === 'content_delta' ||
      parsed.type === 'conversation_attached' ||
      parsed.type === 'qna_response' ||
      parsed.type === 'done' ||
      parsed.type === 'error'
    ) {
      return parsed as QnaStreamEvent;
    }
  } catch {
    return null;
  }
  return null;
}

function fileExtension(filename: string): string {
  const index = filename.lastIndexOf('.');
  return index >= 0 ? filename.slice(index).toLowerCase() : '';
}

function resolvePreviewKind(
  contentType: string | null | undefined,
  filename: string,
): PreviewKind {
  const normalizedType = (contentType || '').toLowerCase();
  const ext = fileExtension(filename);
  if (normalizedType.includes('pdf') || ext === '.pdf') {
    return 'pdf';
  }
  if (
    normalizedType.startsWith('image/') ||
    [
      '.png',
      '.jpg',
      '.jpeg',
      '.gif',
      '.bmp',
      '.tif',
      '.tiff',
      '.webp',
    ].includes(ext)
  ) {
    return 'image';
  }
  return 'unsupported';
}

function formatAssistantAnswer(
  response: QnaAskResponse,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const lines = [
    response.grounded_answer?.text?.trim() || t('ai.qaAssistant.noAnswer'),
  ];
  const hits = buildEvidenceItems(response).slice(0, 8);
  if (hits.length > 0) {
    lines.push('', `**${t('ai.qaAssistant.evidenceTitle')}**`);
    hits.forEach((hit, index) => {
      const title = escapeMarkdown(hit.title);
      const score = typeof hit.score === 'number' ? formatScore(hit.score) : '';
      lines.push(`${index + 1}. ${title}${score ? ` (${score})` : ''}`);
    });
  }
  return lines.join('\n');
}

function buildEvidenceItems(response: QnaAskResponse): EvidenceItem[] {
  const items: EvidenceItem[] = [];
  const seenEvidenceKeys = new Set<string>();
  const citations = response.grounded_answer?.citations ?? [];
  citations.forEach((citation) => {
    const evidenceKey = citation.resource_id;
    if (seenEvidenceKeys.has(evidenceKey)) {
      return;
    }
    seenEvidenceKeys.add(evidenceKey);
    const hit = response.hits.find(
      (candidate) => candidate.resource_id === citation.resource_id,
    );
    items.push({
      title: hit?.title || citation.resource_id,
      score: hit?.score,
    });
  });
  if (items.length > 0) {
    return items;
  }

  response.hits.forEach((hit) => {
    const evidenceKey = hit.resource_id;
    if (seenEvidenceKeys.has(evidenceKey)) {
      return;
    }
    seenEvidenceKeys.add(evidenceKey);
    items.push({
      title: hit.title || hit.resource_id,
      score: hit.score,
    });
  });
  return items;
}

function toChatTurn(turn: ConversationTurn): ChatTurn {
  return turn as ChatTurn;
}

function ConversationHistoryPanel({
  activeConversationId,
  conversations,
  onNewConversation,
  onSelectConversation,
}: {
  activeConversationId: string | null;
  conversations: ConversationSummary[];
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
}) {
  const { t } = useTranslation('apps');
  const [query, setQuery] = useState('');
  const filteredConversations = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return conversations;
    }
    return conversations.filter((conversation) => {
      return conversation.title.toLowerCase().includes(normalized);
    });
  }, [conversations, query]);

  return (
    <aside className="flex max-h-72 min-h-0 flex-col border-b border-app-border bg-app-surface-sidebar/70 lg:max-h-none lg:w-72 lg:shrink-0 lg:border-b-0 lg:border-r">
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-app-border px-3">
        <h2 className="truncate app-text-control text-app-ink">
          {t('ai.qaAssistant.historyTitle')}
        </h2>
        <button
          type="button"
          onClick={onNewConversation}
          className="app-text-control inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2.5 text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
        >
          <Plus size={14} />
          <span>{t('ai.qaAssistant.newConversation')}</span>
        </button>
      </div>
      <div className="border-b border-app-border px-3 py-2">
        <label className="flex h-8 items-center gap-2 rounded-md border border-app-border bg-app-surface px-2 text-app-ink/45 transition-colors focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent/15">
          <Search size={13} />
          <input
            aria-label={t('ai.qaAssistant.searchHistory')}
            className="min-w-0 flex-1 bg-transparent app-text-caption text-app-ink outline-none placeholder:text-app-ink/35"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('ai.qaAssistant.searchHistory')}
          />
        </label>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {conversations.length === 0 ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-ink/45">
            {t('ai.qaAssistant.noHistory')}
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="rounded-md px-2 py-1.5 app-text-caption text-app-ink/45">
            {t('ai.qaAssistant.noHistorySearchResults')}
          </div>
        ) : (
          <ul className="space-y-0.5">
            {filteredConversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => onSelectConversation(conversation.id)}
                    className={cn(
                      'flex h-8 w-full items-center gap-2 rounded-md px-2 text-left transition-colors',
                      isActive
                        ? 'bg-app-surface-hover text-app-accent'
                        : 'text-app-ink/75 hover:bg-app-surface-hover hover:text-app-ink',
                    )}
                  >
                    <MessageSquare
                      size={13}
                      className={cn(
                        'shrink-0',
                        isActive ? 'text-app-accent' : 'text-app-ink/40',
                      )}
                    />
                    <span className="min-w-0 flex-1 truncate app-text-caption">
                      {conversation.title}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}

function AttachmentPreviewModal({
  file,
  onClose,
  onDownload,
}: {
  file: AttachmentPreviewState;
  onClose: () => void;
  onDownload: (documentId: string, filename: string) => void;
}) {
  const { t } = useTranslation('apps');

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/55 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('ai.qaAssistant.previewAttachment', {
        name: file.filename,
      })}
    >
      <div
        style={{
          height: 'min(920px, calc(100vh - 1rem))',
          width: 'min(1400px, calc(100vw - 1rem))',
        }}
        className="flex flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface shadow-2xl"
      >
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-app-border px-4">
          <div className="min-w-0">
            <h2 className="truncate app-text-control text-app-ink">
              {file.filename}
            </h2>
            <p className="truncate app-text-micro text-app-ink/45">
              {file.contentType}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => onDownload(file.documentId, file.filename)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2.5 app-text-control text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
            >
              <Download className="h-4 w-4" />
              {t('ai.qaAssistant.download')}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex size-8 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
              aria-label={t('ai.qaAssistant.closePreview')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 bg-app-bg">
          {file.kind === 'pdf' ? (
            <iframe
              src={file.url}
              title={file.filename}
              className="h-full w-full border-0 bg-white"
            />
          ) : file.kind === 'image' ? (
            <div className="flex h-full items-center justify-center p-4">
              <img
                src={file.url}
                alt={file.filename}
                className="max-h-full max-w-full object-contain"
              />
            </div>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <FileText className="h-10 w-10 text-app-ink/35" />
              <p className="app-text-body-sm font-medium text-app-ink">
                {t('ai.qaAssistant.previewUnsupported')}
              </p>
              <button
                type="button"
                onClick={() => onDownload(file.documentId, file.filename)}
                className="inline-flex h-9 items-center gap-1.5 rounded-md border border-app-border bg-app-surface px-3 app-text-control text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
              >
                <Download className="h-4 w-4" />
                {t('ai.qaAssistant.download')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NoticeDetailModal({
  notice,
  onClose,
  onDownload,
  onPreview,
  previewingFileKey,
}: {
  notice: QnaDocumentDetail;
  onClose: () => void;
  onDownload: (documentId: string, filename: string) => void;
  onPreview: (documentId: string, filename: string) => void;
  previewingFileKey: string | null;
}) {
  const { t } = useTranslation('apps');

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center bg-black/45 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('ai.qaAssistant.noticeDetail')}
    >
      <div
        style={{
          maxHeight: 'min(840px, calc(100vh - 2rem))',
          width: 'min(920px, calc(100vw - 2rem))',
        }}
        className="flex flex-col overflow-hidden rounded-lg border border-app-border bg-app-surface shadow-2xl"
      >
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-app-border px-5 py-4">
          <div className="min-w-0">
            <p className="app-text-micro font-medium text-app-ink/45">
              {t('ai.qaAssistant.noticeDetail')}
            </p>
            <h2 className="mt-1 app-text-body-sm font-semibold text-app-ink">
              {notice.title}
            </h2>
            <p className="mt-1 app-text-caption text-app-ink/50">
              {[notice.author, notice.posted_at].filter(Boolean).join(' · ')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
            aria-label={t('ai.qaAssistant.closePreview')}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <dl className="grid grid-cols-3 gap-3 border-b border-app-border pb-4">
            <div>
              <dt className="app-text-micro text-app-ink/45">
                {t('ai.qaAssistant.attachmentCount')}
              </dt>
              <dd className="mt-1 app-text-caption font-medium text-app-ink">
                {t('ai.qaAssistant.itemCount', {
                  count: notice.attachments.length,
                })}
              </dd>
            </div>
            <div>
              <dt className="app-text-micro text-app-ink/45">
                {t('ai.qaAssistant.indexedChars')}
              </dt>
              <dd className="mt-1 app-text-caption font-medium text-app-ink">
                {notice.char_count.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt className="app-text-micro text-app-ink/45">
                {t('ai.qaAssistant.ragStatus')}
              </dt>
              <dd className="mt-1 app-text-caption font-medium text-app-ink">
                {notice.rag_status}
              </dd>
            </div>
          </dl>

          <section className="border-b border-app-border py-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('ai.qaAssistant.noticeBody')}
            </h3>
            {notice.body_text.trim() ? (
              <MarkdownContent
                content={formatQnaBodyMarkdown(notice.body_text)}
                className="chat-message-markdown custom-scrollbar mt-3 max-h-80 overflow-auto break-words rounded-md border border-app-border bg-app-bg px-3 py-3 text-app-ink/75"
              />
            ) : (
              <p className="mt-3 rounded-md border border-dashed border-app-border px-3 py-4 app-text-caption text-app-ink/45">
                {t('ai.qaAssistant.noNoticeBody')}
              </p>
            )}
          </section>

          <section className="pt-4">
            <h3 className="app-text-caption font-semibold text-app-ink">
              {t('ai.qaAssistant.attachments')}
            </h3>
            {notice.attachments.length === 0 ? (
              <p className="mt-3 rounded-md border border-dashed border-app-border px-3 py-4 app-text-caption text-app-ink/45">
                {t('ai.qaAssistant.noAttachments')}
              </p>
            ) : (
              <ul className="mt-3 divide-y divide-app-border overflow-hidden rounded-md border border-app-border">
                {notice.attachments.map((name) => {
                  const previewKey = `${notice.id}:${name}`;
                  const isPreviewing = previewingFileKey === previewKey;
                  return (
                    <li
                      key={previewKey}
                      className="flex items-center gap-2 bg-app-bg px-3 py-2"
                    >
                      <Paperclip className="h-4 w-4 shrink-0 text-app-ink/45" />
                      <button
                        type="button"
                        onClick={() => onPreview(notice.id, name)}
                        disabled={isPreviewing}
                        className="min-w-0 flex-1 truncate text-left app-text-caption font-medium text-app-ink/80 hover:text-app-accent disabled:opacity-60"
                        title={t('ai.qaAssistant.previewAttachment', {
                          name,
                        })}
                      >
                        {name}
                      </button>
                      <button
                        type="button"
                        onClick={() => onPreview(notice.id, name)}
                        disabled={isPreviewing}
                        className="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-app-border bg-app-surface px-2 app-text-micro text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-60"
                      >
                        {isPreviewing ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <FileText className="h-3.5 w-3.5" />
                        )}
                        {t('ai.qaAssistant.preview')}
                      </button>
                      <button
                        type="button"
                        onClick={() => onDownload(notice.id, name)}
                        className="inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink transition-colors hover:border-app-accent hover:text-app-accent"
                        aria-label={t('ai.qaAssistant.downloadDocument', {
                          name,
                        })}
                      >
                        <Download className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function ResourcePanel({
  documents,
  isAdmin,
  notices,
  onClose,
  onDelete,
  onDownload,
  onPanelError,
  onPreview,
  onSyncBoard,
  onUpload,
  open,
  panelError,
  previewingFileKey,
  syncing,
  token,
  uploading,
}: {
  documents: QnaDocument[];
  isAdmin: boolean;
  notices: QnaDocument[];
  onClose: () => void;
  open: boolean;
  onDelete: (documentId: string) => void;
  onDownload: (documentId: string, filename: string) => void;
  onPanelError: (message: string | null) => void;
  onPreview: (documentId: string, filename: string) => void;
  onSyncBoard: () => void;
  onUpload: (file: File) => void;
  panelError: string | null;
  previewingFileKey: string | null;
  syncing: boolean;
  token: string;
  uploading: boolean;
}) {
  const { t } = useTranslation('apps');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedNotice, setSelectedNotice] =
    useState<QnaDocumentDetail | null>(null);
  const [loadingNoticeId, setLoadingNoticeId] = useState<string | null>(null);

  const openNoticeDetail = useCallback(
    async (notice: QnaDocument) => {
      if (!token || loadingNoticeId) {
        return;
      }
      setLoadingNoticeId(notice.id);
      onPanelError(null);
      try {
        const detail = await getQnaDocument({
          token,
          documentId: notice.id,
        });
        setSelectedNotice(detail);
      } catch (error) {
        onPanelError(
          error instanceof QnaApiError
            ? error.message
            : t('ai.qaAssistant.errors.detailLoadFailed'),
        );
      } finally {
        setLoadingNoticeId((current) =>
          current === notice.id ? null : current,
        );
      }
    },
    [loadingNoticeId, onPanelError, t, token],
  );

  return (
    <>
      {open && (
        <button
          type="button"
          aria-label={t('ai.qaAssistant.closeResourcePanel')}
          onClick={onClose}
          className="fixed inset-0 z-40 bg-black/40 min-[1181px]:hidden"
        />
      )}
      <aside
        className={cn(
          'flex shrink-0 flex-col border-l border-app-border bg-app-surface',
          // Wide screens: inline column.
          'min-[1181px]:relative min-[1181px]:w-80',
          // Narrow screens: right slide-over drawer toggled from the header.
          'max-[1180px]:fixed max-[1180px]:inset-y-0 max-[1180px]:right-0 max-[1180px]:z-50 max-[1180px]:w-[min(20rem,85vw)] max-[1180px]:shadow-2xl max-[1180px]:transition-transform max-[1180px]:duration-200',
          open
            ? 'max-[1180px]:translate-x-0'
            : 'max-[1180px]:hidden max-[1180px]:translate-x-full',
        )}
      >
        <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-app-border px-4">
          <h2 className="min-w-0 truncate app-text-control text-app-ink">
            {t('ai.qaAssistant.resourcePanelTitle')}
          </h2>
          <div className="flex shrink-0 items-center gap-2">
            {isAdmin && (
              <button
                type="button"
                onClick={onSyncBoard}
                disabled={syncing}
                className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2 app-text-control text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
                title={t('ai.qaAssistant.syncBoardDescription')}
              >
                {syncing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                <span>{t('ai.qaAssistant.syncBoard')}</span>
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label={t('ai.qaAssistant.closeResourcePanel')}
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-app-border bg-app-bg text-app-ink transition-colors hover:border-app-accent hover:text-app-accent min-[1181px]:hidden"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {isAdmin && (
          <section className="shrink-0 border-b border-app-border bg-app-surface px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="app-text-caption font-semibold text-app-ink">
                {t('ai.qaAssistant.documents')}
              </h3>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="inline-flex h-7 items-center gap-1 rounded-md border border-app-border bg-app-bg px-2 app-text-micro text-app-ink transition-colors hover:border-app-accent hover:text-app-accent disabled:opacity-50"
              >
                {uploading ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Upload className="h-3 w-3" />
                )}
                {t('ai.qaAssistant.uploadDocument')}
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept={UPLOAD_ACCEPT}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  onUpload(file);
                }
                event.target.value = '';
              }}
            />
            {documents.length === 0 ? (
              <p className="mt-2 rounded-md border border-dashed border-app-border px-3 py-3 app-text-caption text-app-ink/45">
                {t('ai.qaAssistant.noDocuments')}
              </p>
            ) : (
              <div className="custom-scrollbar mt-2 max-h-36 overflow-y-auto pr-1">
                <ul className="space-y-1">
                  {documents.map((doc) => (
                    <li
                      key={doc.id}
                      className="flex items-center gap-2 rounded-md border border-app-border bg-app-bg px-2 py-1.5"
                    >
                      <FileText className="h-3.5 w-3.5 shrink-0 text-app-ink/45" />
                      <button
                        type="button"
                        onClick={() => onPreview(doc.id, doc.title)}
                        disabled={
                          previewingFileKey === `${doc.id}:${doc.title}`
                        }
                        className="min-w-0 flex-1 truncate text-left app-text-caption text-app-ink/75 hover:text-app-accent"
                        title={t('ai.qaAssistant.previewAttachment', {
                          name: doc.title,
                        })}
                      >
                        {doc.title}
                      </button>
                      <button
                        type="button"
                        onClick={() => onDownload(doc.id, doc.title)}
                        className="shrink-0 text-app-ink/45 hover:text-app-accent"
                        aria-label={t('ai.qaAssistant.downloadDocument', {
                          name: doc.title,
                        })}
                      >
                        <Download className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => onDelete(doc.id)}
                        className="shrink-0 text-app-ink/45 hover:text-app-danger"
                        aria-label={t('ai.qaAssistant.deleteDocument')}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
          {panelError && (
            <p className="mb-3 flex items-start gap-1 rounded-md border border-app-danger-border bg-app-danger-bg px-2 py-1.5 app-text-caption text-app-danger-text dark:border-app-danger-border dark:bg-app-danger-bg dark:text-app-danger-text">
              <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" />
              {panelError}
            </p>
          )}

          <section>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="app-text-caption font-semibold text-app-ink">
                {t('ai.qaAssistant.notices')}
              </h3>
              <span className="app-text-micro text-app-ink/45">
                {t('ai.qaAssistant.itemCount', { count: notices.length })}
              </span>
            </div>
            {notices.length === 0 ? (
              <p className="rounded-md border border-dashed border-app-border px-3 py-4 app-text-caption text-app-ink/45">
                {t('ai.qaAssistant.noNotices')}
              </p>
            ) : (
              <ul className="divide-y divide-app-border overflow-hidden rounded-md border border-app-border bg-app-bg">
                {notices.map((notice) => (
                  <li key={notice.id}>
                    <button
                      type="button"
                      onClick={() => {
                        void openNoticeDetail(notice);
                      }}
                      disabled={loadingNoticeId !== null}
                      className="block w-full px-3 py-2 text-left transition-colors hover:bg-app-surface-hover disabled:cursor-wait disabled:opacity-70"
                      title={t('ai.qaAssistant.openNoticeDetail', {
                        name: notice.title,
                      })}
                    >
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span className="block min-w-0 flex-1 truncate app-text-caption font-medium text-app-ink">
                          {notice.title}
                        </span>
                        {loadingNoticeId === notice.id && (
                          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-app-ink/45" />
                        )}
                      </span>
                      <span className="mt-1 flex items-center gap-1.5 app-text-micro text-app-ink/45">
                        <span className="min-w-0 truncate">
                          {[notice.author, notice.posted_at]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                        {notice.attachments.length > 0 && (
                          <span className="inline-flex shrink-0 items-center gap-0.5 rounded border border-app-border bg-app-surface px-1 text-app-ink/55">
                            <Paperclip className="h-3 w-3" />
                            {notice.attachments.length}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </aside>
      {selectedNotice && (
        <NoticeDetailModal
          notice={selectedNotice}
          onClose={() => setSelectedNotice(null)}
          onDownload={onDownload}
          onPreview={onPreview}
          previewingFileKey={previewingFileKey}
        />
      )}
    </>
  );
}

export function QaAssistantView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const isAdmin = user?.system_roles?.includes('platform_admin') ?? false;
  const authToken = token ?? '';
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<
    string | null
  >(null);
  const [activeConversation, setActiveConversation] =
    useState<ConversationDetail | null>(null);
  const [activeTurns, setActiveTurns] = useState<ChatTurn[]>([]);
  const [draftTitle, setDraftTitle] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [liveAnswer, setLiveAnswer] = useState('');
  const [chatError, setChatError] = useState<string | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  // Resource panel is inline on wide screens; on narrow screens it opens as a
  // right slide-over drawer toggled from the chat header.
  const [resourceOpen, setResourceOpen] = useState(false);
  const [documents, setDocuments] = useState<QnaDocument[]>([]);
  const [notices, setNotices] = useState<QnaDocument[]>([]);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [previewingFileKey, setPreviewingFileKey] = useState<string | null>(
    null,
  );
  const [previewFile, setPreviewFile] = useState<AttachmentPreviewState | null>(
    null,
  );

  const turns = activeTurns;

  const loadConversationDetail = useCallback(
    async (conversationId: string) => {
      if (!authToken || !workspaceSlug) {
        return;
      }
      const detail = await getConversation(authToken, conversationId, {
        workspaceSlug,
      });
      setActiveConversation(detail);
      setActiveConversationId(detail.id);
      setActiveTurns(detail.turns.map(toChatTurn));
      setDraftTitle(null);
    },
    [authToken, workspaceSlug],
  );

  const refreshConversationList = useCallback(async () => {
    if (!authToken || !workspaceSlug) {
      setConversations([]);
      return [];
    }
    const result = await listConversations(authToken, {
      limit: 50,
      scopeRef: 'qna_assistant',
      scopeResourceId: 'company',
      workspaceSlug,
    });
    setConversations(result.items);
    return result.items;
  }, [authToken, workspaceSlug]);

  useEffect(() => {
    if (!authToken || !workspaceSlug) {
      setConversations([]);
      setActiveConversation(null);
      setActiveConversationId(null);
      setActiveTurns([]);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const items = await refreshConversationList();
        if (cancelled) {
          return;
        }
        const first = items[0] ?? null;
        if (first) {
          await loadConversationDetail(first.id);
        } else {
          setActiveConversation(null);
          setActiveConversationId(null);
          setActiveTurns([]);
        }
      } catch {
        if (!cancelled) {
          setConversations([]);
          setActiveConversation(null);
          setActiveConversationId(null);
          setActiveTurns([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    authToken,
    loadConversationDetail,
    refreshConversationList,
    workspaceSlug,
  ]);

  useEffect(() => {
    return () => {
      if (previewFile?.url) {
        URL.revokeObjectURL(previewFile.url);
      }
    };
  }, [previewFile?.url]);

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

  const refreshLists = useCallback(async () => {
    if (!authToken) {
      return;
    }
    try {
      const [docsResult, noticesResult] = await Promise.all([
        listQnaDocuments({ token: authToken }),
        listQnaNotices({ token: authToken }),
      ]);
      setDocuments(docsResult.documents);
      setNotices(noticesResult.notices);
      setPanelError(null);
    } catch (error) {
      setPanelError(
        error instanceof QnaApiError
          ? error.message
          : t('ai.qaAssistant.errors.loadFailed'),
      );
    }
  }, [authToken, t]);

  useEffect(() => {
    void refreshLists();
  }, [refreshLists]);

  const handleAsk = useCallback(
    async (overrideQuestion?: string) => {
      const trimmed = (overrideQuestion ?? question).trim();
      if (!trimmed || asking || !authToken || !workspaceSlug) {
        return;
      }

      const requestedConversationId = activeConversationId;
      let attachedConversationId = requestedConversationId;
      const userTurn: ChatTurn = {
        id: createId('qna-user'),
        seq: turns.length + 1,
        role: 'user',
        content: trimmed,
        responseStatus: 'done',
      };
      setActiveTurns((current) => [...current, userTurn]);
      if (!requestedConversationId) {
        setDraftTitle(buildConversationTitle(trimmed));
      }

      setQuestion('');
      setAsking(true);
      setLiveAnswer('');
      setChatError(null);
      streamAbortRef.current?.abort();
      const controller = new AbortController();
      streamAbortRef.current = controller;
      try {
        const response = await streamQna({
          token: authToken,
          question: trimmed,
          conversationId: requestedConversationId,
          workspaceSlug,
          signal: controller.signal,
        });
        if (!response.body) {
          throw new QnaApiError(0, t('ai.qaAssistant.errors.connect'));
        }

        let finalResponse: QnaAskResponse | null = null;
        for await (const message of iterSseEvents(
          response.body,
          controller.signal,
        )) {
          const event = parseQnaStreamEvent(message.data);
          if (!event) {
            continue;
          }
          if (event.type === 'conversation_attached') {
            attachedConversationId = event.data.conversation_id;
            setActiveConversationId(attachedConversationId);
            continue;
          }
          if (event.type === 'content_delta') {
            setLiveAnswer((current) => `${current}${event.data.text}`);
            continue;
          }
          if (event.type === 'qna_response') {
            finalResponse = event.data.response;
            continue;
          }
          if (event.type === 'error') {
            throw new QnaApiError(0, event.data.message);
          }
          if (event.type === 'done') {
            break;
          }
        }
        if (!finalResponse) {
          throw new QnaApiError(0, t('ai.qaAssistant.errors.askFailed'));
        }
        setActiveTurns((current) => [
          ...current,
          {
            id: createId('qna-assistant'),
            role: 'assistant',
            content: formatAssistantAnswer(finalResponse, t),
            responseStatus: 'done',
            finishReason: 'stop',
          },
        ]);
        await refreshConversationList();
        if (attachedConversationId) {
          await loadConversationDetail(attachedConversationId);
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          return;
        }
        const message =
          error instanceof QnaApiError
            ? error.message
            : t('ai.qaAssistant.errors.askFailed');
        setChatError(message);
        setActiveTurns((current) => [
          ...current,
          {
            id: createId('qna-assistant-error'),
            role: 'assistant',
            content: message,
            responseStatus: 'error',
            finishReason: 'error',
          },
        ]);
        await refreshConversationList();
        if (attachedConversationId) {
          await loadConversationDetail(attachedConversationId);
        }
      } finally {
        if (streamAbortRef.current === controller) {
          streamAbortRef.current = null;
        }
        setLiveAnswer('');
        setAsking(false);
      }
    },
    [
      activeConversationId,
      asking,
      authToken,
      loadConversationDetail,
      question,
      refreshConversationList,
      t,
      turns.length,
      workspaceSlug,
    ],
  );

  const handleUpload = useCallback(
    async (file: File) => {
      if (!authToken) {
        return;
      }
      setUploading(true);
      setPanelError(null);
      try {
        await uploadQnaDocument({ token: authToken, file });
        await refreshLists();
      } catch (error) {
        setPanelError(
          error instanceof QnaApiError
            ? error.message
            : t('ai.qaAssistant.errors.uploadFailed'),
        );
      } finally {
        setUploading(false);
      }
    },
    [authToken, refreshLists, t],
  );

  const handleDelete = useCallback(
    async (documentId: string) => {
      if (!authToken) {
        return;
      }
      try {
        await deleteQnaDocument({
          token: authToken,
          documentId,
        });
        await refreshLists();
      } catch (error) {
        setPanelError(
          error instanceof QnaApiError
            ? error.message
            : t('ai.qaAssistant.errors.deleteFailed'),
        );
      }
    },
    [authToken, refreshLists, t],
  );

  const handleDownload = useCallback(
    async (documentId: string, filename: string) => {
      if (!authToken) {
        return;
      }
      try {
        await downloadQnaFile({
          token: authToken,
          documentId,
          filename,
        });
      } catch (error) {
        setPanelError(
          error instanceof QnaApiError
            ? error.message
            : t('ai.qaAssistant.errors.downloadFailed'),
        );
      }
    },
    [authToken, t],
  );

  const handlePreview = useCallback(
    async (documentId: string, filename: string) => {
      if (!authToken) {
        return;
      }
      const previewKey = `${documentId}:${filename}`;
      setPreviewingFileKey(previewKey);
      setPanelError(null);
      try {
        const file = await fetchQnaFileBlob({
          token: authToken,
          documentId,
          filename,
        });
        const url = URL.createObjectURL(file.blob);
        setPreviewFile({
          documentId,
          filename: file.filename,
          url,
          contentType: file.contentType,
          kind: resolvePreviewKind(file.contentType, file.filename),
        });
      } catch (error) {
        setPanelError(
          error instanceof QnaApiError
            ? error.message
            : t('ai.qaAssistant.errors.previewFailed'),
        );
      } finally {
        setPreviewingFileKey((current) =>
          current === previewKey ? null : current,
        );
      }
    },
    [authToken, t],
  );

  const handleSyncBoard = useCallback(async () => {
    if (!authToken || syncing) {
      return;
    }
    setSyncing(true);
    setPanelError(null);
    try {
      await syncQnaBoard({ token: authToken });
      await refreshLists();
    } catch (error) {
      setPanelError(
        error instanceof QnaApiError
          ? error.message
          : t('ai.qaAssistant.errors.syncFailed'),
      );
    } finally {
      setSyncing(false);
    }
  }, [authToken, syncing, refreshLists, t]);

  const suggestionsRaw = t('ai.qaAssistant.suggestions', {
    returnObjects: true,
  }) as unknown;
  const suggestions = Array.isArray(suggestionsRaw)
    ? (suggestionsRaw as string[])
    : [];

  const composer = (
    <ChatComposer
      input={question}
      onInputChange={setQuestion}
      onSubmit={() => {
        void handleAsk();
      }}
      onAbort={() => streamAbortRef.current?.abort()}
      isSending={asking}
      isStreaming={asking}
      chatError={chatError}
      placeholder={t('ai.qaAssistant.placeholder')}
      isDisabled={!authToken || !workspaceSlug}
      leadingControls={null}
    />
  );

  return (
    <main className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-app-bg lg:flex-row">
      <ConversationHistoryPanel
        activeConversationId={activeConversationId}
        conversations={conversations}
        onNewConversation={() => {
          setActiveConversationId(null);
          setActiveConversation(null);
          setActiveTurns([]);
          setDraftTitle(null);
          setQuestion('');
          setChatError(null);
        }}
        onSelectConversation={(conversationId) => {
          void loadConversationDetail(conversationId);
          setChatError(null);
        }}
      />

      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-app-bg">
        <header className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-app-border bg-app-surface px-4">
          <div className="flex min-w-0 items-center gap-2">
            <MessageSquare size={15} className="shrink-0 text-app-ink/40" />
            <h1 className="min-w-0 truncate app-text-control text-app-ink">
              {activeConversation?.title ??
                draftTitle ??
                t('ai.qaAssistant.title')}
            </h1>
          </div>
          <button
            type="button"
            onClick={() => setResourceOpen(true)}
            className="app-text-control inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md border border-app-border bg-app-bg px-2.5 text-app-ink transition-colors hover:border-app-accent hover:text-app-accent min-[1181px]:hidden"
          >
            <FileText size={14} />
            <span>{t('ai.qaAssistant.resourcePanelTitle')}</span>
          </button>
        </header>

        {turns.length === 0 && !asking ? (
          <div className="custom-scrollbar flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-6 py-10">
            <div className="w-full max-w-2xl">
              <div className="mb-7 text-center">
                <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-app-accent/10 text-app-accent">
                  <MessageSquare size={22} />
                </div>
                <h2 className="app-text-title-lg text-app-ink">
                  {t('ai.qaAssistant.emptyGreeting')}
                </h2>
                <p className="mx-auto mt-2 max-w-md app-text-body-sm text-app-ink/55 dark:text-app-ink/65">
                  {t('ai.qaAssistant.emptySubline')}
                </p>
              </div>
              {composer}
              {suggestions.length > 0 && (
                <div className="mt-5">
                  <p className="mb-2 text-center app-text-micro font-medium text-app-ink/40">
                    {t('ai.qaAssistant.suggestionsTitle')}
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => void handleAsk(suggestion)}
                        disabled={asking || !authToken || !workspaceSlug}
                        className="app-text-caption rounded-full border border-app-border bg-app-surface px-3 py-1.5 text-app-ink/70 transition-colors hover:border-app-accent hover:text-app-accent focus-visible:border-app-accent focus-visible:outline-none disabled:opacity-50"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            <ChatThread
              turns={turns}
              typingLabel={t('ai.qaAssistant.thinking')}
              jumpToBottomLabel={t('ai.qaAssistant.jumpToBottom')}
              liveAssistant={
                asking
                  ? {
                      content: liveAnswer,
                      reasoning: '',
                      status: 'streaming',
                    }
                  : null
              }
              onCopyTurn={async (turn) => {
                await navigator.clipboard?.writeText(turn.content);
              }}
            />
            <div className="sticky bottom-0 z-10 space-y-2 border-t border-app-border bg-app-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
              {composer}
            </div>
          </>
        )}
      </section>

      <ResourcePanel
        documents={documents}
        isAdmin={isAdmin}
        notices={notices}
        open={resourceOpen}
        onClose={() => setResourceOpen(false)}
        onDelete={(documentId) => {
          void handleDelete(documentId);
        }}
        onDownload={(documentId, filename) => {
          void handleDownload(documentId, filename);
        }}
        onPanelError={setPanelError}
        onPreview={(documentId, filename) => {
          void handlePreview(documentId, filename);
        }}
        onSyncBoard={() => {
          void handleSyncBoard();
        }}
        onUpload={(file) => {
          void handleUpload(file);
        }}
        panelError={panelError}
        previewingFileKey={previewingFileKey}
        syncing={syncing}
        token={authToken}
        uploading={uploading}
      />
      {previewFile && (
        <AttachmentPreviewModal
          file={previewFile}
          onClose={() => setPreviewFile(null)}
          onDownload={(documentId, filename) => {
            void handleDownload(documentId, filename);
          }}
        />
      )}
    </main>
  );
}
