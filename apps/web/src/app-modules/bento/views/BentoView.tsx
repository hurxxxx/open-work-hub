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
  Sparkles,
  Trash2,
  Users,
  X,
} from 'lucide-react';
import { DropdownMenu, type DropdownItem } from '@open-work-hub/ui';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  formatDateTime,
  normalizeTimeZone,
} from '@/src/platform/time/time-utils';
import {
  archiveBentoDocument,
  createBentoDocument,
  editBentoDocumentWithAi,
  generateBentoDocument,
  getBentoAiJob,
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
  buildBentoHubPath,
  buildBentoPresentationPath,
} from '../bento-route-paths';
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
  return workspaceSlug ? buildBentoHubPath(workspaceSlug) : '/';
}

function documentPath(
  workspaceSlug: string | undefined,
  documentId: string,
): string {
  return workspaceSlug
    ? buildBentoPresentationPath(workspaceSlug, documentId)
    : '/';
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
  const [aiDialogOpen, setAiDialogOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiSlideCount, setAiSlideCount] = useState(6);
  const [aiVisibility, setAiVisibility] = useState<BentoVisibility>('personal');
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
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

  const handleAiGenerate = useCallback(async () => {
    const prompt = aiPrompt.trim();
    if (!token || prompt.length < 3 || aiGenerating) return;
    setAiGenerating(true);
    setAiError(null);
    try {
      await generateBentoDocument(
        token,
        {
          prompt,
          slide_count: aiSlideCount,
          language: i18n.language.startsWith('ko') ? 'ko' : 'en',
          visibility: aiVisibility,
        },
        workspaceSlug,
      );
      setAiPrompt('');
      setAiDialogOpen(false);
    } catch (caught) {
      setAiError(
        caught instanceof Error
          ? caught.message
          : t('apps:bento.aiGenerateFailed'),
      );
    } finally {
      setAiGenerating(false);
    }
  }, [
    aiGenerating,
    aiPrompt,
    aiSlideCount,
    aiVisibility,
    i18n.language,
    t,
    token,
    workspaceSlug,
  ]);

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
                onClick={() => {
                  setAiError(null);
                  setAiDialogOpen(true);
                }}
                className="inline-flex h-9 items-center gap-2 rounded-md bg-app-success px-3 text-sm font-semibold text-white hover:bg-app-success/90"
              >
                <Sparkles size={15} />
                {t('apps:bento.aiCreate')}
              </button>
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

      {aiDialogOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !aiGenerating) {
              setAiDialogOpen(false);
            }
          }}
        >
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="bento-ai-dialog-title"
            className="w-full max-w-2xl rounded-xl border border-app-border bg-app-surface p-5 shadow-2xl"
            onSubmit={(event) => {
              event.preventDefault();
              void handleAiGenerate();
            }}
          >
            <div className="flex items-start gap-3">
              <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-app-success/10 text-app-success">
                <Sparkles size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="bento-ai-dialog-title" className="app-text-title-sm">
                  {t('apps:bento.aiDialogTitle')}
                </h2>
                <p className="app-text-body-sm mt-1 text-app-ink/55">
                  {t('apps:bento.aiDialogDescription')}
                </p>
              </div>
              <button
                type="button"
                aria-label={t('apps:bento.aiClose')}
                disabled={aiGenerating}
                onClick={() => setAiDialogOpen(false)}
                className="inline-flex size-9 items-center justify-center rounded-md text-app-ink/55 hover:bg-app-surface-hover disabled:opacity-40"
              >
                <X size={18} />
              </button>
            </div>

            <label className="mt-5 block">
              <span className="app-text-label-sm text-app-ink/75">
                {t('apps:bento.aiPromptLabel')}
              </span>
              <textarea
                autoFocus
                value={aiPrompt}
                disabled={aiGenerating}
                onChange={(event) => setAiPrompt(event.target.value)}
                placeholder={t('apps:bento.aiPromptPlaceholder')}
                rows={8}
                maxLength={12_000}
                className="app-text-body-sm mt-2 w-full resize-y rounded-lg border border-app-border bg-app-bg px-3 py-3 text-app-ink outline-none placeholder:text-app-ink/35 focus:border-app-success disabled:opacity-60"
              />
            </label>

            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <label>
                <span className="app-text-label-sm text-app-ink/75">
                  {t('apps:bento.aiSlideCount')}
                </span>
                <select
                  value={aiSlideCount}
                  disabled={aiGenerating}
                  onChange={(event) =>
                    setAiSlideCount(Number(event.target.value))
                  }
                  className="app-text-body-sm mt-2 h-10 w-full rounded-md border border-app-border bg-app-bg px-3 text-app-ink outline-none focus:border-app-success"
                >
                  {[3, 4, 5, 6, 8, 10, 12].map((count) => (
                    <option key={count} value={count}>
                      {t('apps:bento.aiSlideCountOption', { count })}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span className="app-text-label-sm text-app-ink/75">
                  {t('apps:bento.aiVisibility')}
                </span>
                <select
                  value={aiVisibility}
                  disabled={aiGenerating}
                  onChange={(event) =>
                    setAiVisibility(event.target.value as BentoVisibility)
                  }
                  className="app-text-body-sm mt-2 h-10 w-full rounded-md border border-app-border bg-app-bg px-3 text-app-ink outline-none focus:border-app-success"
                >
                  <option value="personal">
                    {t('apps:bento.visibilityPersonal')}
                  </option>
                  <option value="workspace">
                    {t('apps:bento.visibilityWorkspace')}
                  </option>
                </select>
              </label>
            </div>

            {aiError ? (
              <div className="mt-4 rounded-md border border-app-danger-border bg-app-danger-bg px-3 py-2 text-sm text-app-danger-text">
                {aiError}
              </div>
            ) : null}

            <div className="mt-5 flex items-center justify-between gap-4 border-t border-app-border pt-4">
              <p className="app-text-caption text-app-ink/45">
                {aiGenerating
                  ? t('apps:bento.aiGeneratingHint')
                  : t('apps:bento.aiLocalHint')}
              </p>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  disabled={aiGenerating}
                  onClick={() => setAiDialogOpen(false)}
                  className="inline-flex h-9 items-center rounded-md border border-app-border px-3 text-sm font-medium text-app-ink/70 disabled:opacity-40"
                >
                  {t('apps:bento.aiCancel')}
                </button>
                <button
                  type="submit"
                  disabled={aiPrompt.trim().length < 3 || aiGenerating}
                  className="inline-flex h-9 items-center gap-2 rounded-md bg-app-success px-4 text-sm font-semibold text-white hover:bg-app-success/90 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {aiGenerating ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Sparkles size={15} />
                  )}
                  {aiGenerating
                    ? t('apps:bento.aiGenerating')
                    : t('apps:bento.aiGenerate')}
                </button>
              </div>
            </div>
          </form>
        </div>
      ) : null}
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
  const { t, i18n } = useTranslation('apps');
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
  const documentRequestRef = useRef<{
    resolve: (documentJson: string) => void;
    reject: (error: Error) => void;
    timeout: ReturnType<typeof setTimeout>;
  } | null>(null);
  const operationChainRef = useRef<Promise<void>>(Promise.resolve());
  const [detail, setDetail] = useState<BentoDocumentDetail | null>(null);
  const [iframeReady, setIframeReady] = useState(false);
  const [saveStatus, setSaveStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const [error, setError] = useState<string | null>(null);
  const [aiEditOpen, setAiEditOpen] = useState(false);
  const [aiEditPrompt, setAiEditPrompt] = useState('');
  const [aiEditing, setAiEditing] = useState(false);
  const [aiEditError, setAiEditError] = useState<string | null>(null);
  const [activeAiEditJobId, setActiveAiEditJobId] = useState<string | null>(
    null,
  );
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
    if (!activeAiEditJobId || !token || !documentId) return undefined;
    let active = true;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const job = await getBentoAiJob(
          token,
          activeAiEditJobId,
          workspaceSlug,
        );
        if (!active) return;
        if (job.status === 'succeeded') {
          if (job.result_document_id === documentId) {
            const revised = await getBentoDocument(
              token,
              documentId,
              workspaceSlug,
            );
            if (!active) return;
            loadedDocumentRef.current = null;
            applyDetail(revised);
            lastSavedJsonRef.current = revised.document_json;
          }
          setSaveStatus('saved');
          setActiveAiEditJobId(null);
          return;
        }
        if (job.status === 'failed' || job.status === 'cancelled') {
          setSaveStatus(job.status === 'failed' ? 'error' : 'saved');
          if (job.status === 'failed') {
            setError(job.error_code || t('bento.aiEditFailed'));
          }
          setActiveAiEditJobId(null);
          return;
        }
        timeoutId = setTimeout(() => void poll(), 2_000);
      } catch (caught) {
        if (!active) return;
        setSaveStatus('error');
        setError(
          caught instanceof Error ? caught.message : t('bento.aiEditFailed'),
        );
        setActiveAiEditJobId(null);
      }
    };

    void poll();
    return () => {
      active = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [activeAiEditJobId, applyDetail, documentId, t, token, workspaceSlug]);

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
        if (message.type === 'save-request' && documentRequestRef.current) {
          const pending = documentRequestRef.current;
          documentRequestRef.current = null;
          clearTimeout(pending.timeout);
          pending.resolve(message.documentJson);
          return;
        }
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
      if (documentRequestRef.current) {
        clearTimeout(documentRequestRef.current.timeout);
        documentRequestRef.current.reject(
          new Error('Bento document request cancelled'),
        );
        documentRequestRef.current = null;
      }
    },
    [],
  );

  const requestCurrentDocument = useCallback((): Promise<string> => {
    if (!iframeReady || !embedConfig || documentRequestRef.current) {
      return Promise.reject(new Error(t('bento.bridgeFailed')));
    }
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        documentRequestRef.current = null;
        reject(new Error(t('bento.bridgeFailed')));
      }, 5_000);
      documentRequestRef.current = { resolve, reject, timeout };
      postToBento(buildBentoSaveRequestMessage());
    });
  }, [embedConfig, iframeReady, postToBento, t]);

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

  const handleAiEdit = useCallback(async () => {
    const prompt = aiEditPrompt.trim();
    if (!token || !documentId || !detail || prompt.length < 3 || aiEditing) {
      return;
    }
    setAiEditing(true);
    setAiEditError(null);
    try {
      await operationChainRef.current.catch(() => undefined);
      if (pendingSaveTimerRef.current) {
        clearTimeout(pendingSaveTimerRef.current);
        pendingSaveTimerRef.current = null;
      }
      const currentDocumentJson = await requestCurrentDocument();
      let current = detailRef.current;
      if (!current) throw new Error(t('bento.loadFailed'));

      if (currentDocumentJson !== lastSavedJsonRef.current) {
        setSaveStatus('saving');
        const saved = await updateBentoDocument(
          token,
          documentId,
          { version: current.version, document_json: currentDocumentJson },
          workspaceSlug,
        );
        applyDetail(saved);
        detailRef.current = saved;
        lastSavedJsonRef.current = saved.document_json;
        current = saved;
      }

      const job = await editBentoDocumentWithAi(
        token,
        documentId,
        {
          version: current.version,
          prompt,
          language: i18n.language.startsWith('ko') ? 'ko' : 'en',
        },
        workspaceSlug,
      );
      setActiveAiEditJobId(job.id);
      setSaveStatus('saving');
      setAiEditPrompt('');
      setAiEditOpen(false);
    } catch (caught) {
      setSaveStatus('error');
      setAiEditError(
        caught instanceof Error ? caught.message : t('bento.aiEditFailed'),
      );
    } finally {
      setAiEditing(false);
    }
  }, [
    aiEditPrompt,
    aiEditing,
    applyDetail,
    detail,
    documentId,
    i18n.language,
    requestCurrentDocument,
    t,
    token,
    workspaceSlug,
  ]);

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
          onClick={() => {
            setAiEditError(null);
            setAiEditOpen(true);
          }}
          disabled={!detail || !iframeReady || aiEditing}
          title={t('bento.aiEdit')}
          className="inline-flex h-9 items-center gap-2 rounded-md bg-app-success px-3 text-sm font-semibold text-white hover:bg-app-success/90 disabled:opacity-40"
        >
          <Sparkles size={16} />
          <span className="hidden lg:inline">{t('bento.aiEdit')}</span>
        </button>
        <button
          type="button"
          onClick={() => postToBento(buildBentoSaveRequestMessage())}
          disabled={!iframeReady || aiEditing}
          title={t('bento.saveNow')}
          className="inline-flex size-9 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink/65 disabled:opacity-40"
        >
          <Save size={16} />
        </button>
        <button
          type="button"
          onClick={() => postToBento(buildBentoExportMessage())}
          disabled={!iframeReady || aiEditing}
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

      <div className="relative flex min-h-0 flex-1 bg-white">
        <div className="relative min-w-0 flex-1">
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
              className={cn(
                'h-full w-full border-0',
                aiEditing && 'pointer-events-none opacity-80',
              )}
              sandbox="allow-downloads allow-forms allow-modals allow-pointer-lock allow-popups allow-presentation allow-same-origin allow-scripts"
              referrerPolicy="strict-origin"
              allow="clipboard-read; clipboard-write; fullscreen"
              allowFullScreen
            />
          ) : null}
        </div>

        {aiEditOpen ? (
          <aside className="relative z-20 flex w-[min(380px,92vw)] shrink-0 flex-col border-l border-app-border bg-app-bg shadow-xl">
            <div className="flex items-start gap-3 border-b border-app-border p-4">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-app-success/10 text-app-success">
                <Sparkles size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="app-text-title-sm">{t('bento.aiEditTitle')}</h2>
                <p className="app-text-caption mt-1 text-app-ink/50">
                  {t('bento.aiEditDescription')}
                </p>
              </div>
              <button
                type="button"
                aria-label={t('bento.aiEditClose')}
                disabled={aiEditing}
                onClick={() => setAiEditOpen(false)}
                className="inline-flex size-8 items-center justify-center rounded-md text-app-ink/55 hover:bg-app-surface-hover disabled:opacity-40"
              >
                <X size={17} />
              </button>
            </div>

            <form
              className="flex min-h-0 flex-1 flex-col p-4"
              onSubmit={(event) => {
                event.preventDefault();
                void handleAiEdit();
              }}
            >
              <label className="flex min-h-0 flex-1 flex-col">
                <span className="app-text-label-sm text-app-ink/75">
                  {t('bento.aiEditPromptLabel')}
                </span>
                <textarea
                  autoFocus
                  value={aiEditPrompt}
                  disabled={aiEditing}
                  onChange={(event) => setAiEditPrompt(event.target.value)}
                  placeholder={t('bento.aiEditPromptPlaceholder')}
                  maxLength={12_000}
                  className="app-text-body-sm mt-2 min-h-48 flex-1 resize-none rounded-lg border border-app-border bg-app-surface px-3 py-3 text-app-ink outline-none placeholder:text-app-ink/35 focus:border-app-success disabled:opacity-60"
                />
              </label>

              {aiEditError ? (
                <div className="mt-3 rounded-md border border-app-danger-border bg-app-danger-bg px-3 py-2 text-sm text-app-danger-text">
                  {aiEditError}
                </div>
              ) : null}

              <p className="app-text-caption mt-3 text-app-ink/45">
                {aiEditing ? t('bento.aiEditingHint') : t('bento.aiEditHint')}
              </p>
              <div className="mt-4 flex justify-end gap-2 border-t border-app-border pt-4">
                <button
                  type="button"
                  disabled={aiEditing}
                  onClick={() => setAiEditOpen(false)}
                  className="inline-flex h-9 items-center rounded-md border border-app-border px-3 text-sm font-medium text-app-ink/70 disabled:opacity-40"
                >
                  {t('bento.aiCancel')}
                </button>
                <button
                  type="submit"
                  disabled={aiEditPrompt.trim().length < 3 || aiEditing}
                  className="inline-flex h-9 items-center gap-2 rounded-md bg-app-success px-4 text-sm font-semibold text-white hover:bg-app-success/90 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  {aiEditing ? (
                    <Loader2 size={15} className="animate-spin" />
                  ) : (
                    <Sparkles size={15} />
                  )}
                  {aiEditing ? t('bento.aiEditing') : t('bento.aiEditApply')}
                </button>
              </div>
            </form>
          </aside>
        ) : null}
      </div>
    </main>
  );
}
