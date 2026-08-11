import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Archive,
  ArrowLeft,
  Download,
  FileUp,
  Loader2,
  Lock,
  MoreHorizontal,
  Plus,
  Presentation,
  Save,
  Search,
  Trash2,
  Users,
} from 'lucide-react';
import { DropdownMenu, type DropdownItem } from '@open-work-hub/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';
import {
  archiveBentoDocument,
  createBentoDocument,
  getBentoDocument,
  listBentoDocuments,
  permanentlyDeleteBentoDocument,
  restoreBentoDocument,
  updateBentoDocument,
  type BentoDocumentDetail,
  type BentoDocumentItem,
  type BentoHubView,
  type BentoVisibility,
} from '../api/bento-api';
import {
  buildBentoExportMessage,
  buildBentoLoadMessage,
  buildBentoSaveRequestMessage,
  BentoImportError,
  currentBentoEmbedConfig,
  isBentoMessageOriginAllowed,
  parseBentoBridgeMessage,
  parseBentoHtmlDocument,
} from './bento-embed-protocol';

function hubPath(workspaceSlug: string | undefined): string {
  return workspaceSlug ? buildWorkspaceAppPath(workspaceSlug, 'bento') : '/';
}

function documentPath(
  workspaceSlug: string | undefined,
  documentId: string,
): string {
  return `${hubPath(workspaceSlug)}/${encodeURIComponent(documentId)}`;
}

function viewFromSearch(value: string | null): BentoHubView {
  return value === 'mine' || value === 'archived' ? value : 'all';
}

export function BentoView() {
  const { documentId } = useParams();
  return documentId ? <BentoEditor /> : <BentoHub />;
}

function BentoHub() {
  const { t, i18n } = useTranslation(['apps', 'shell']);
  const { token, user } = useAuth();
  const { workspaceSlug } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [items, setItems] = useState<BentoDocumentItem[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const view = viewFromSearch(searchParams.get('view'));
  const archived = view === 'archived';
  const timeZone = normalizeTimeZone(user?.time_zone);
  const personalItems = useMemo(
    () => items.filter((item) => item.visibility === 'personal'),
    [items],
  );
  const workspaceItems = useMemo(
    () => items.filter((item) => item.visibility === 'workspace'),
    [items],
  );

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listBentoDocuments(
        token,
        { view, q: query },
        workspaceSlug,
      );
      setItems(response.items);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : t('apps:bento.loadFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [query, t, token, view, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = useCallback(
    async (visibility: BentoVisibility) => {
      if (!token) return;
      setError(null);
      try {
        const created = await createBentoDocument(
          token,
          { title: t('apps:bento.untitled'), visibility },
          workspaceSlug,
        );
        navigate(documentPath(workspaceSlug, created.id));
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:bento.createFailed'),
        );
      }
    },
    [navigate, t, token, workspaceSlug],
  );

  const handleImport = useCallback(
    async (file: File) => {
      if (!token) return;
      setError(null);
      try {
        const parsed = parseBentoHtmlDocument(await file.text());
        const created = await createBentoDocument(
          token,
          {
            title: parsed.title,
            visibility: 'personal',
            document_json: parsed.documentJson,
          },
          workspaceSlug,
        );
        navigate(documentPath(workspaceSlug, created.id));
      } catch (caught) {
        setError(
          caught instanceof BentoImportError
            ? t('apps:bento.importFailed')
            : caught instanceof Error
              ? caught.message
              : t('apps:bento.importFailed'),
        );
      } finally {
        if (importInputRef.current) importInputRef.current.value = '';
      }
    },
    [navigate, t, token, workspaceSlug],
  );

  const updateItem = useCallback((updated: BentoDocumentItem) => {
    setItems((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
  }, []);

  const renameItem = useCallback(
    async (item: BentoDocumentItem) => {
      if (!token) return;
      const title = window
        .prompt(t('apps:bento.renamePrompt'), item.title)
        ?.trim();
      if (!title || title === item.title) return;
      try {
        updateItem(
          await updateBentoDocument(
            token,
            item.id,
            { version: item.version, title },
            workspaceSlug,
          ),
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:bento.renameFailed'),
        );
      }
    },
    [t, token, updateItem, workspaceSlug],
  );

  const changeVisibility = useCallback(
    async (item: BentoDocumentItem, visibility: BentoVisibility) => {
      if (!token || visibility === item.visibility) return;
      try {
        updateItem(
          await updateBentoDocument(
            token,
            item.id,
            { version: item.version, visibility },
            workspaceSlug,
          ),
        );
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:bento.visibilityUpdateFailed'),
        );
      }
    },
    [t, token, updateItem, workspaceSlug],
  );

  const archiveItem = useCallback(
    async (item: BentoDocumentItem) => {
      if (!token) return;
      try {
        await archiveBentoDocument(token, item.id, workspaceSlug);
        setItems((current) => current.filter((entry) => entry.id !== item.id));
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:bento.archiveFailed'),
        );
      }
    },
    [t, token, workspaceSlug],
  );

  const restoreItem = useCallback(
    async (item: BentoDocumentItem) => {
      if (!token) return;
      try {
        await restoreBentoDocument(token, item.id, workspaceSlug);
        setItems((current) => current.filter((entry) => entry.id !== item.id));
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:bento.restoreFailed'),
        );
      }
    },
    [t, token, workspaceSlug],
  );

  const deleteItem = useCallback(
    async (item: BentoDocumentItem) => {
      if (!token || !window.confirm(t('apps:bento.deleteConfirm'))) return;
      try {
        await permanentlyDeleteBentoDocument(token, item.id, workspaceSlug);
        setItems((current) => current.filter((entry) => entry.id !== item.id));
      } catch (caught) {
        setError(
          caught instanceof Error
            ? caught.message
            : t('apps:bento.deleteFailed'),
        );
      }
    },
    [t, token, workspaceSlug],
  );

  const viewTitle =
    view === 'mine'
      ? t('shell:nav.bento-mine')
      : view === 'archived'
        ? t('shell:nav.bento-archived')
        : t('shell:nav.bento-all');

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-app-bg text-app-ink">
      <div className="border-b border-app-border px-6 py-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Presentation size={20} className="text-app-success" />
              <h1 className="app-text-title-lg">{viewTitle}</h1>
            </div>
            <p className="app-text-body-sm mt-1 text-app-ink/50">
              {t('apps:bento.count', { count: items.length })}
            </p>
          </div>
          {!archived ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={importInputRef}
                type="file"
                accept=".html,.bento.html,text/html"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handleImport(file);
                }}
              />
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-sm font-medium hover:bg-app-surface-hover"
              >
                <FileUp size={15} />
                {t('apps:bento.import')}
              </button>
              <button
                type="button"
                onClick={() => void handleCreate('personal')}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-app-ink px-3 text-sm font-medium text-app-bg hover:bg-app-ink/90"
              >
                <Plus size={15} />
                {t('apps:bento.createPersonal')}
              </button>
            </div>
          ) : null}
        </div>
        <label className="mt-4 flex h-9 max-w-md items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-app-ink/60">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('apps:bento.search')}
            className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
          />
        </label>
      </div>

      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-6 py-2 text-sm text-app-danger-text">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {loading ? (
          <div className="flex min-h-[280px] items-center justify-center text-app-ink/45">
            <Loader2 size={24} className="animate-spin" />
          </div>
        ) : (
          <div className="space-y-8">
            <BentoSection
              title={t('apps:bento.personalSectionTitle')}
              empty={t(
                archived
                  ? 'apps:bento.archiveEmpty'
                  : 'apps:bento.personalSectionEmpty',
              )}
              icon={Lock}
              items={personalItems}
              archived={archived}
              timeZone={timeZone}
              locale={i18n.language}
              onCreate={() => void handleCreate('personal')}
              onOpen={(item) => navigate(documentPath(workspaceSlug, item.id))}
              onRename={(item) => void renameItem(item)}
              onVisibilityChange={(item, visibility) =>
                void changeVisibility(item, visibility)
              }
              onArchive={(item) => void archiveItem(item)}
              onRestore={(item) => void restoreItem(item)}
              onDelete={(item) => void deleteItem(item)}
            />
            <BentoSection
              title={t('apps:bento.workspaceSectionTitle')}
              empty={t(
                archived
                  ? 'apps:bento.archiveEmpty'
                  : 'apps:bento.workspaceSectionEmpty',
              )}
              icon={Users}
              items={workspaceItems}
              archived={archived}
              timeZone={timeZone}
              locale={i18n.language}
              onCreate={() => void handleCreate('workspace')}
              onOpen={(item) => navigate(documentPath(workspaceSlug, item.id))}
              onRename={(item) => void renameItem(item)}
              onVisibilityChange={(item, visibility) =>
                void changeVisibility(item, visibility)
              }
              onArchive={(item) => void archiveItem(item)}
              onRestore={(item) => void restoreItem(item)}
              onDelete={(item) => void deleteItem(item)}
            />
          </div>
        )}
      </div>
    </main>
  );
}

function BentoSection({
  title,
  empty,
  icon: Icon,
  items,
  archived,
  timeZone,
  locale,
  onCreate,
  onOpen,
  onRename,
  onVisibilityChange,
  onArchive,
  onRestore,
  onDelete,
}: {
  title: string;
  empty: string;
  icon: typeof Lock;
  items: BentoDocumentItem[];
  archived: boolean;
  timeZone: string;
  locale: string;
  onCreate: () => void;
  onOpen: (item: BentoDocumentItem) => void;
  onRename: (item: BentoDocumentItem) => void;
  onVisibilityChange: (
    item: BentoDocumentItem,
    visibility: BentoVisibility,
  ) => void;
  onArchive: (item: BentoDocumentItem) => void;
  onRestore: (item: BentoDocumentItem) => void;
  onDelete: (item: BentoDocumentItem) => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon size={17} className="text-app-ink/55" />
          <h2 className="app-text-title-md">{title}</h2>
          <span className="rounded-full bg-app-surface px-2 py-0.5 text-xs text-app-ink/50">
            {items.length}
          </span>
        </div>
        {!archived ? (
          <button
            type="button"
            onClick={onCreate}
            className="inline-flex h-8 items-center gap-2 rounded-md border border-app-border bg-app-surface px-3 text-sm hover:bg-app-surface-hover"
          >
            <Plus size={14} />
            {t('bento.create')}
          </button>
        ) : null}
      </div>
      {items.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {items.map((item) => (
            <BentoCard
              key={item.id}
              item={item}
              archived={archived}
              timeZone={timeZone}
              locale={locale}
              onOpen={() => onOpen(item)}
              onRename={() => onRename(item)}
              onVisibilityChange={(visibility) =>
                onVisibilityChange(item, visibility)
              }
              onArchive={() => onArchive(item)}
              onRestore={() => onRestore(item)}
              onDelete={() => onDelete(item)}
            />
          ))}
        </div>
      ) : (
        <div className="flex min-h-36 items-center justify-center rounded-lg border border-dashed border-app-border bg-app-surface/40 px-6 text-sm text-app-ink/45">
          {empty}
        </div>
      )}
    </section>
  );
}

function BentoCard({
  item,
  archived,
  timeZone,
  locale,
  onOpen,
  onRename,
  onVisibilityChange,
  onArchive,
  onRestore,
  onDelete,
}: {
  item: BentoDocumentItem;
  archived: boolean;
  timeZone: string;
  locale: string;
  onOpen: () => void;
  onRename: () => void;
  onVisibilityChange: (visibility: BentoVisibility) => void;
  onArchive: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation('apps');
  const menuItems: DropdownItem[] = archived
    ? [
        {
          id: 'restore',
          label: t('bento.restore'),
          disabled: !item.can_manage,
          onSelect: onRestore,
        },
        {
          id: 'delete',
          label: t('bento.deletePermanently'),
          disabled: !item.can_manage,
          separatorBefore: true,
          onSelect: onDelete,
        },
      ]
    : [
        {
          id: 'rename',
          label: t('bento.rename'),
          disabled: !item.can_manage,
          onSelect: onRename,
        },
        {
          id: 'personal',
          label: t('bento.changeToPersonal'),
          disabled: !item.can_manage || item.visibility === 'personal',
          separatorBefore: true,
          onSelect: () => onVisibilityChange('personal'),
        },
        {
          id: 'workspace',
          label: t('bento.changeToWorkspace'),
          disabled: !item.can_manage || item.visibility === 'workspace',
          onSelect: () => onVisibilityChange('workspace'),
        },
        {
          id: 'archive',
          label: t('bento.archive'),
          disabled: !item.can_manage,
          separatorBefore: true,
          onSelect: onArchive,
        },
      ];

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpen();
        }
      }}
      className="group overflow-hidden rounded-lg border border-app-border bg-app-surface shadow-sm transition hover:-translate-y-0.5 hover:border-amber-500/45 hover:shadow-md"
    >
      <div className="relative flex aspect-[16/9] items-center justify-center bg-gradient-to-br from-amber-50 to-orange-100 dark:from-amber-950/30 dark:to-orange-950/20">
        <Presentation size={36} className="text-amber-600/70" />
        <div
          className="absolute right-2 top-2"
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <DropdownMenu
            align="end"
            side="bottom"
            trigger={
              <button
                type="button"
                aria-label={t('bento.actionsMenu')}
                className="inline-flex size-8 items-center justify-center rounded-md border border-app-border bg-app-bg/95 text-app-ink/65 shadow-sm"
              >
                <MoreHorizontal size={16} />
              </button>
            }
            items={menuItems}
          />
        </div>
      </div>
      <div className="border-t border-app-border p-4">
        <p className="app-text-title-sm truncate">{item.title}</p>
        <p className="app-text-body-sm mt-2 text-app-ink/50">
          {t('bento.updated', {
            date: formatDateTime(item.updated_at, {
              fallback: '-',
              locale,
              month: 'short',
              day: 'numeric',
              year: 'numeric',
              hour: 'numeric',
              minute: '2-digit',
              timeZone,
            }),
          })}
        </p>
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-app-border px-2 py-1 text-xs text-app-ink/55">
          {item.visibility === 'workspace' ? (
            <Users size={13} className="text-app-success" />
          ) : (
            <Lock size={13} />
          )}
          {t(
            item.visibility === 'workspace'
              ? 'bento.visibilityWorkspace'
              : 'bento.visibilityPersonal',
          )}
        </div>
      </div>
    </article>
  );
}

function BentoEditor() {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const { workspaceSlug, documentId } = useParams();
  const navigate = useNavigate();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const detailRef = useRef<BentoDocumentDetail | null>(null);
  const loadedDocumentRef = useRef<string | null>(null);
  const lastSavedJsonRef = useRef<string | null>(null);
  const pendingSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const operationChainRef = useRef<Promise<void>>(Promise.resolve());
  const [detail, setDetail] = useState<BentoDocumentDetail | null>(null);
  const [iframeReady, setIframeReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const [error, setError] = useState<string | null>(null);
  const embedConfig = useMemo(() => currentBentoEmbedConfig(), []);

  const applyDetail = useCallback((next: BentoDocumentDetail) => {
    detailRef.current = next;
    setDetail(next);
  }, []);

  const postToBento = useCallback(
    (message: object) => {
      if (!embedConfig) return;
      iframeRef.current?.contentWindow?.postMessage(
        message,
        embedConfig.origin,
      );
    },
    [embedConfig],
  );

  const enqueuePatch = useCallback(
    (patch: { document_json?: string; visibility?: BentoVisibility }) => {
      const operation = operationChainRef.current
        .catch(() => undefined)
        .then(async () => {
          const current = detailRef.current;
          if (!token || !documentId || !current) return;
          setSaveStatus('saving');
          setError(null);
          const updated = await updateBentoDocument(
            token,
            documentId,
            { version: current.version, ...patch },
            workspaceSlug,
          );
          applyDetail(updated);
          lastSavedJsonRef.current = updated.document_json;
          setSaveStatus('saved');
        })
        .catch((caught: unknown) => {
          setSaveStatus('error');
          setError(
            caught instanceof Error ? caught.message : t('bento.saveFailed'),
          );
        });
      operationChainRef.current = operation;
      return operation;
    },
    [applyDetail, documentId, t, token, workspaceSlug],
  );

  const queueDocumentSave = useCallback(
    (documentJson: string, immediate = false) => {
      if (documentJson === lastSavedJsonRef.current) return;
      if (pendingSaveTimerRef.current) {
        clearTimeout(pendingSaveTimerRef.current);
      }
      pendingSaveTimerRef.current = setTimeout(
        () => {
          pendingSaveTimerRef.current = null;
          void enqueuePatch({ document_json: documentJson });
        },
        immediate ? 0 : 650,
      );
    },
    [enqueuePatch],
  );

  useEffect(() => {
    if (!token || !documentId) return undefined;
    let active = true;
    detailRef.current = null;
    loadedDocumentRef.current = null;
    lastSavedJsonRef.current = null;
    setDetail(null);
    setError(null);
    setSaveStatus('idle');
    getBentoDocument(token, documentId, workspaceSlug)
      .then((loaded) => {
        if (!active) return;
        applyDetail(loaded);
        lastSavedJsonRef.current = loaded.document_json;
      })
      .catch((caught: Error) => {
        if (active) setError(caught.message || t('bento.loadFailed'));
      });
    return () => {
      active = false;
    };
  }, [applyDetail, documentId, t, token, workspaceSlug]);

  useEffect(() => {
    if (!iframeReady || !detail || !embedConfig) return;
    if (loadedDocumentRef.current === detail.id) return;
    loadedDocumentRef.current = detail.id;
    postToBento(buildBentoLoadMessage(detail.document_json));
  }, [detail, embedConfig, iframeReady, postToBento]);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (
        !embedConfig ||
        !isBentoMessageOriginAllowed(event.origin, embedConfig.origin) ||
        event.source !== iframeRef.current?.contentWindow
      ) {
        return;
      }
      const message = parseBentoBridgeMessage(event.data);
      if (!message) return;
      if (message.type === 'ready') {
        loadedDocumentRef.current = null;
        setIframeReady(true);
        return;
      }
      if (message.type === 'loaded') {
        setSaveStatus('saved');
        return;
      }
      if (
        (message.type === 'document-changed' ||
          message.type === 'save-request') &&
        message.documentJson
      ) {
        queueDocumentSave(
          message.documentJson,
          message.type === 'save-request',
        );
        return;
      }
      if (message.type === 'error') {
        setSaveStatus('error');
        setError(message.message || t('bento.bridgeFailed'));
      }
    }
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [embedConfig, queueDocumentSave, t]);

  useEffect(
    () => () => {
      if (pendingSaveTimerRef.current) {
        clearTimeout(pendingSaveTimerRef.current);
      }
    },
    [],
  );

  const goBack = useCallback(() => {
    navigate(hubPath(workspaceSlug));
  }, [navigate, workspaceSlug]);

  const handleVisibilityChange = useCallback(
    (visibility: BentoVisibility) => {
      if (!detail || visibility === detail.visibility) return;
      void enqueuePatch({ visibility });
    },
    [detail, enqueuePatch],
  );

  const handleArchive = useCallback(async () => {
    if (!token || !documentId) return;
    try {
      await operationChainRef.current.catch(() => undefined);
      await archiveBentoDocument(token, documentId, workspaceSlug);
      goBack();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : t('bento.archiveFailed'),
      );
    }
  }, [documentId, goBack, t, token, workspaceSlug]);

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-app-bg text-app-ink">
      <div className="flex min-h-[60px] items-center gap-3 border-b border-app-border bg-app-bg px-4 py-2">
        <button
          type="button"
          onClick={goBack}
          title={t('bento.back')}
          className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 hover:text-app-ink"
        >
          <ArrowLeft size={17} />
        </button>
        <Presentation size={18} className="text-amber-600" />
        <h1 className="app-text-title-sm min-w-0 flex-1 truncate">
          {detail?.title ?? t('bento.loading')}
        </h1>
        <div
          className={cn(
            'hidden min-w-[72px] items-center justify-center rounded-full px-2 py-1 text-xs sm:inline-flex',
            saveStatus === 'error'
              ? 'bg-app-danger-bg text-app-danger-text'
              : 'bg-app-surface text-app-ink/55',
          )}
        >
          {saveStatus === 'saving' ? (
            <Loader2 size={13} className="mr-1 animate-spin" />
          ) : null}
          {t(`bento.${saveStatus}`)}
        </div>
        <button
          type="button"
          onClick={() => postToBento(buildBentoSaveRequestMessage())}
          disabled={!iframeReady}
          title={t('bento.saveNow')}
          className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 disabled:opacity-40"
        >
          <Save size={16} />
        </button>
        <button
          type="button"
          onClick={() => postToBento(buildBentoExportMessage())}
          disabled={!iframeReady}
          title={t('bento.export')}
          className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 disabled:opacity-40"
        >
          <Download size={16} />
        </button>
        {detail ? (
          <DropdownMenu
            align="end"
            side="bottom"
            trigger={
              <button
                type="button"
                aria-label={t('bento.actionsMenu')}
                className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65"
              >
                <MoreHorizontal size={16} />
              </button>
            }
            items={[
              {
                id: 'personal',
                label: t('bento.changeToPersonal'),
                disabled:
                  !detail.can_manage || detail.visibility === 'personal',
                onSelect: () => handleVisibilityChange('personal'),
              },
              {
                id: 'workspace',
                label: t('bento.changeToWorkspace'),
                disabled:
                  !detail.can_manage || detail.visibility === 'workspace',
                onSelect: () => handleVisibilityChange('workspace'),
              },
            ]}
          />
        ) : null}
        {detail?.can_manage ? (
          <button
            type="button"
            onClick={() => void handleArchive()}
            title={t('bento.archive')}
            className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 hover:text-app-danger-text"
          >
            <Trash2 size={16} />
          </button>
        ) : null}
      </div>

      {error ? (
        <div className="border-b border-app-danger-border bg-app-danger-bg px-4 py-2 text-sm text-app-danger-text">
          {error}
        </div>
      ) : null}

      <div className="relative min-h-0 flex-1 bg-white">
        {!detail || !embedConfig ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-app-bg text-app-ink/50">
            {!embedConfig ? (
              t('bento.notConfigured')
            ) : error ? (
              <Archive size={24} />
            ) : (
              <Loader2 size={24} className="animate-spin" />
            )}
          </div>
        ) : null}
        {embedConfig ? (
          <iframe
            ref={iframeRef}
            title={t('bento.editorTitle')}
            src={embedConfig.src}
            className="h-full w-full border-0"
            sandbox="allow-downloads allow-forms allow-modals allow-pointer-lock allow-popups allow-presentation allow-same-origin allow-scripts"
            referrerPolicy="strict-origin"
            allow="clipboard-read; clipboard-write; fullscreen"
            allowFullScreen
          />
        ) : null}
      </div>
    </main>
  );
}
