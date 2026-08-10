import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { motion } from 'motion/react';
import {
  ArrowLeft,
  ExternalLink,
  History,
  Loader2,
  Pencil,
  Plus,
  Scale,
  Trash2,
} from 'lucide-react';

import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  InlineNotice,
  Input,
  SearchField,
  useConfirm,
  useToast,
} from '@open-alm/ui';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasAnySystemRole } from '@/src/platform/auth/auth-api';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import {
  type ByPartResponse,
  type ByRegionResponse,
  type ByTypeResponse,
  type CompetitorOut,
  type CompetitorSpecOut,
  type CompetitorSpecsResponse,
  type HistoryEntry,
  type LawItemOut,
  type LawItemRaw,
  type LawItemWriteIn,
  type PartGroupOut,
  type PartsResponse,
  type RegionOut,
  type RegionsResponse,
  type TypeOut,
  type TypesResponse,
  createItem,
  deleteItem,
  fetchByPart,
  fetchByRegion,
  fetchByType,
  fetchCompetitorSpecs,
  fetchCompetitors,
  fetchItemRaw,
  fetchParts,
  fetchRegions,
  fetchSearch,
  fetchTypes,
  updateItem,
} from '../../api/lawsearch-api';
import { cn } from '@/src/lib/utils';

type TabId = 'parts' | 'regions' | 'types' | 'competitors';
type AppsT = (key: string, options?: Record<string, unknown>) => string;

type Detail =
  | { kind: 'part'; id: string; data: ByPartResponse | null }
  | { kind: 'region'; id: string; data: ByRegionResponse | null }
  | { kind: 'type'; id: string; data: ByTypeResponse | null }
  | { kind: 'competitor'; id: string; data: CompetitorSpecsResponse | null }
  | { kind: 'search'; q: string; items: LawItemOut[] };

// 원본 Flask 앱과 동일하게 탭은 3개. 경쟁사는 '규제 유형별' 카드 안의
// 가상 카드("competitors")를 통해서만 진입한다.
const TABS: { id: TabId; key: string }[] = [
  { id: 'parts', key: 'tabs.parts' },
  { id: 'regions', key: 'tabs.regions' },
  { id: 'types', key: 'tabs.types' },
];

function safeExternalUrl(rawUrl: string | undefined): string | null {
  const value = rawUrl?.trim();
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function SourceUrlLink({ sourceUrl }: { sourceUrl?: string }) {
  const safeUrl = safeExternalUrl(sourceUrl);
  if (!safeUrl) {
    return <span className="text-app-ink/35">—</span>;
  }
  return (
    <a
      href={safeUrl}
      target="_blank"
      rel="noreferrer"
      className="inline-flex h-7 w-7 items-center justify-center rounded text-app-accent hover:bg-app-surface-hover"
      title={safeUrl}
    >
      <ExternalLink size={14} />
    </a>
  );
}

export function LawSearchView() {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ?? resolveShellWorkspaceSlug(user, null);
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirm();

  const isAdmin = hasAnySystemRole(user, ['platform_admin']);

  const [tab, setTab] = useState<TabId>('parts');
  const [parts, setParts] = useState<PartsResponse | null>(null);
  const [regions, setRegions] = useState<RegionsResponse | null>(null);
  const [types, setTypes] = useState<TypesResponse | null>(null);
  const [competitors, setCompetitors] = useState<CompetitorOut[]>([]);
  const [loadingCards, setLoadingCards] = useState(false);
  const [cardsError, setCardsError] = useState<string | null>(null);

  const [detail, setDetail] = useState<Detail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const searchTimer = useRef<number | null>(null);

  const [historyFor, setHistoryFor] = useState<LawItemOut | null>(null);
  const [editing, setEditing] = useState<{ mode: 'create' | 'edit'; item: LawItemRaw | null } | null>(null);

  // ── Load cards for current tab ──────────────────────────────────
  const reloadCards = useCallback(
    async (which: TabId) => {
      if (!workspaceSlug) return;
      setLoadingCards(true);
      setCardsError(null);
      try {
        if (which === 'parts') {
          setParts(await fetchParts(token, workspaceSlug));
        } else if (which === 'regions') {
          setRegions(await fetchRegions(token, workspaceSlug));
        } else if (which === 'types') {
          setTypes(await fetchTypes(token, workspaceSlug));
        } else if (which === 'competitors') {
          const res = await fetchCompetitors(token, workspaceSlug);
          setCompetitors(res.competitors);
        }
      } catch (e) {
        setCardsError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoadingCards(false);
      }
    },
    [token, workspaceSlug],
  );

  const ensureEditMasters = useCallback(async () => {
    if (!workspaceSlug) return false;
    try {
      const [nextParts, nextRegions, nextTypes] = await Promise.all([
        parts ? Promise.resolve(parts) : fetchParts(token, workspaceSlug),
        regions ? Promise.resolve(regions) : fetchRegions(token, workspaceSlug),
        types ? Promise.resolve(types) : fetchTypes(token, workspaceSlug),
      ]);
      setParts(nextParts);
      setRegions(nextRegions);
      setTypes(nextTypes);
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
      return false;
    }
  }, [parts, regions, toast, token, types, workspaceSlug]);

  useEffect(() => {
    if (!token || !workspaceSlug) return;
    void reloadCards(tab);
  }, [tab, token, workspaceSlug, reloadCards]);

  // ── Open detail ─────────────────────────────────────────────────
  const openDetail = useCallback(
    async (kind: Detail['kind'], id: string) => {
      if (!workspaceSlug) return;
      if (kind === 'search') return;
      setDetail({ kind, id, data: null } as Detail);
      setLoadingDetail(true);
      try {
        let data: ByPartResponse | ByRegionResponse | ByTypeResponse | CompetitorSpecsResponse;
        if (kind === 'part') data = await fetchByPart(token, workspaceSlug, id);
        else if (kind === 'region') data = await fetchByRegion(token, workspaceSlug, id);
        else if (kind === 'type') data = await fetchByType(token, workspaceSlug, id);
        else data = await fetchCompetitorSpecs(token, workspaceSlug, id);
        setDetail({ kind, id, data } as Detail);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
        setDetail(null);
      } finally {
        setLoadingDetail(false);
      }
    },
    [token, toast, workspaceSlug],
  );

  const reloadDetail = useCallback(async () => {
    if (!detail || !workspaceSlug) return;
    if (detail.kind === 'search') {
      // re-run search
      const res = await fetchSearch(token, workspaceSlug, detail.q);
      setDetail({ kind: 'search', q: detail.q, items: res.items });
      return;
    }
    await openDetail(detail.kind, detail.id);
  }, [detail, openDetail, token, workspaceSlug]);

  // ── Search ──────────────────────────────────────────────────────
  useEffect(() => {
    if (searchTimer.current !== null) {
      window.clearTimeout(searchTimer.current);
    }
    const q = searchTerm.trim();
    if (!q || !workspaceSlug) {
      setDetail((current) => (current?.kind === 'search' ? null : current));
      return;
    }
    searchTimer.current = window.setTimeout(async () => {
      setLoadingDetail(true);
      try {
        const res = await fetchSearch(token, workspaceSlug, q);
        setDetail({ kind: 'search', q, items: res.items });
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
      } finally {
        setLoadingDetail(false);
      }
    }, 300);
    return () => {
      if (searchTimer.current !== null) window.clearTimeout(searchTimer.current);
    };
  }, [searchTerm, token, toast, workspaceSlug]);

  // ── Admin actions ───────────────────────────────────────────────
  const openCreate = useCallback(async () => {
    if (!isAdmin) return;
    if (!(await ensureEditMasters())) return;
    setEditing({ mode: 'create', item: null });
  }, [ensureEditMasters, isAdmin]);

  const openEdit = useCallback(
    async (itemId: string) => {
      if (!isAdmin) return;
      try {
        if (!workspaceSlug) return;
        if (!(await ensureEditMasters())) return;
        const raw = await fetchItemRaw(token, workspaceSlug, itemId);
        setEditing({ mode: 'edit', item: raw });
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    },
    [ensureEditMasters, isAdmin, token, toast, workspaceSlug],
  );

  const handleDelete = useCallback(
    async (itemId: string, itemName: string) => {
      if (!isAdmin) return;
      const ok = await confirm({
        title: t('ai.lawSearch.delete.title'),
        description: t('ai.lawSearch.delete.description', { name: itemName }),
        confirmLabel: t('ai.lawSearch.actions.delete'),
        cancelLabel: t('ai.lawSearch.actions.cancel'),
        variant: 'danger',
      });
      if (!ok) return;
      try {
        if (!workspaceSlug) return;
        await deleteItem(token, workspaceSlug, itemId);
        toast.success(t('ai.lawSearch.delete.success'));
        void reloadDetail();
        void reloadCards(tab);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : String(e));
      }
    },
    [confirm, isAdmin, reloadCards, reloadDetail, t, tab, toast, token, workspaceSlug],
  );

  const breadcrumb = useMemo(() => detailBreadcrumb(detail, t), [detail, t]);
  const detailTitle = useMemo(() => detailTitleText(detail, t), [detail, t]);

  return (
    <div className="relative flex h-full min-w-0 flex-col">
      <header className="border-b border-app-border bg-app-bg px-4 pt-4 lg:px-6 lg:pt-3">
        <nav className="app-text-caption mb-1.5 hidden min-w-0 items-center gap-1.5 text-app-ink/50 lg:flex">
          <span className="shrink-0">{t('ai.lawSearch.title')}</span>
          {breadcrumb ? (
            <>
              <span className="shrink-0 text-app-ink/35">/</span>
              <span className="truncate">{breadcrumb}</span>
            </>
          ) : null}
        </nav>

        <div className="mb-3 flex min-w-0 items-start justify-between gap-3 lg:items-center lg:gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-app-accent text-app-accent-fg lg:h-7 lg:w-7">
              <Scale size={16} />
            </div>
            <div className="min-w-0">
              <h1 className="app-text-title-md min-w-0 truncate text-app-ink">
                {t('ai.lawSearch.title')}
              </h1>
              {detailTitle ? (
                <p className="app-text-caption mt-0.5 truncate text-app-ink/45">
                  {detailTitle}
                </p>
              ) : null}
            </div>
            {detail ? (
              <button
                type="button"
                onClick={() => {
                  setDetail(null);
                  setSearchTerm('');
                }}
                className="app-text-control-sm ml-1 inline-flex h-7 shrink-0 items-center gap-1 rounded text-app-ink/65 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
              >
                <ArrowLeft size={14} />
                <span className="hidden sm:inline">{t('ai.lawSearch.back')}</span>
              </button>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <div className="w-56 lg:w-72">
              <SearchField
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder={t('ai.lawSearch.searchPlaceholder')}
              />
            </div>
          </div>
        </div>

        {/* Tab row */}
        <div className="relative -mb-px flex items-center gap-1">
          {TABS.map((it) => {
            const active = !detail && tab === it.id;
            return (
              <button
                key={it.id}
                type="button"
                onClick={() => {
                  setTab(it.id);
                  setDetail(null);
                  setSearchTerm('');
                }}
                className={cn(
                  'relative app-text-control-sm rounded-t px-3 py-2 transition-colors',
                  active
                    ? 'text-app-ink'
                    : 'text-app-ink/55 hover:text-app-ink',
                )}
              >
                {t(`ai.lawSearch.${it.key}`)}
                {active ? (
                  <motion.span
                    layoutId="lawsearch-tab-underline"
                    className="absolute bottom-0 left-0 right-0 h-0.5 bg-app-accent"
                  />
                ) : null}
              </button>
            );
          })}
        </div>
      </header>

      <main className="custom-scrollbar flex-1 overflow-y-auto p-4 lg:p-6">
        {confirmDialog}

        {cardsError && !detail ? (
          <InlineNotice tone="danger" className="mb-4">
            {cardsError}
          </InlineNotice>
        ) : null}

        {!detail ? (
          <CardSection
            tab={tab}
            loading={loadingCards}
            parts={parts}
            regions={regions}
            types={types}
            competitors={competitors}
            onOpenPart={(id) => openDetail('part', id)}
            onOpenRegion={(id) => openDetail('region', id)}
            onOpenType={(id) => {
              if (id === 'competitors') {
                setTab('competitors');
                setDetail(null);
              } else {
                openDetail('type', id);
              }
            }}
            onOpenCompetitor={(id) => openDetail('competitor', id)}
          />
        ) : (
          <DetailSection
            detail={detail}
            loading={loadingDetail}
            isAdmin={isAdmin}
            onShowHistory={(it) => setHistoryFor(it)}
            onAdd={() => void openCreate()}
            onEdit={(id) => void openEdit(id)}
            onDelete={(id, name) => void handleDelete(id, name)}
          />
        )}
      </main>

      <HistoryDialog
        item={historyFor}
        onClose={() => setHistoryFor(null)}
      />

      {editing ? (
        <ItemEditDialog
          mode={editing.mode}
          item={editing.item}
          parts={parts}
          regions={regions}
          types={types}
          context={detail}
          workspaceSlug={workspaceSlug}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void reloadDetail();
            void reloadCards(tab);
          }}
        />
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Breadcrumb / title helpers
// ─────────────────────────────────────────────────────────────────

function detailBreadcrumb(detail: Detail | null, t: AppsT): string | null {
  if (!detail) return null;
  if (detail.kind === 'search') return t('ai.lawSearch.searchBreadcrumb', { query: detail.q });
  if (detail.kind === 'part' && detail.data) return detail.data.part.name_ko;
  if (detail.kind === 'region' && detail.data) return detail.data.region.name_ko;
  if (detail.kind === 'type' && detail.data) return detail.data.type.name_ko;
  if (detail.kind === 'competitor' && detail.data) return detail.data.company.name_ko;
  return '...';
}

function detailTitleText(detail: Detail | null, t: AppsT): string | null {
  if (!detail) return null;
  if (detail.kind === 'search') return `"${detail.q}"`;
  return detailBreadcrumb(detail, t);
}

// ─────────────────────────────────────────────────────────────────
// CardSection — tab body when not in detail view
// ─────────────────────────────────────────────────────────────────

interface CardSectionProps {
  tab: TabId;
  loading: boolean;
  parts: PartsResponse | null;
  regions: RegionsResponse | null;
  types: TypesResponse | null;
  competitors: CompetitorOut[];
  onOpenPart: (id: string) => void;
  onOpenRegion: (id: string) => void;
  onOpenType: (id: string) => void;
  onOpenCompetitor: (id: string) => void;
}

function CardSection(props: CardSectionProps) {
  const { t } = useTranslation('apps');
  if (props.loading) return <LoadingBlock />;
  if (props.tab === 'parts') {
    if (!props.parts) return <EmptyState title={t('ai.lawSearch.empty.parts')} />;
    return (
      <div className="space-y-6">
        {props.parts.groups.map((g) => (
          <PartGroupBlock key={g.id} group={g} onOpen={props.onOpenPart} />
        ))}
      </div>
    );
  }
  if (props.tab === 'regions') {
    if (!props.regions) return <EmptyState title={t('ai.lawSearch.empty.regions')} />;
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {props.regions.regions.map((r) => (
          <RegionCard key={r.id} region={r} onClick={() => props.onOpenRegion(r.id)} />
        ))}
      </div>
    );
  }
  if (props.tab === 'types') {
    if (!props.types) return <EmptyState title={t('ai.lawSearch.empty.types')} />;
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {props.types.types.map((t2) => (
          <TypeCard key={t2.id} type={t2} onClick={() => props.onOpenType(t2.id)} />
        ))}
      </div>
    );
  }
  if (props.tab === 'competitors') {
    if (!props.competitors.length)
      return <EmptyState title={t('ai.lawSearch.empty.competitors')} />;
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {props.competitors.map((c) => (
          <CompetitorCard
            key={c.id}
            competitor={c}
            onClick={() => props.onOpenCompetitor(c.id)}
          />
        ))}
      </div>
    );
  }
  return null;
}

function PartGroupBlock({
  group,
  onOpen,
}: {
  group: PartGroupOut;
  onOpen: (id: string) => void;
}) {
  return (
    <section className="rounded-2xl border border-app-border bg-app-surface p-4 lg:p-5">
      <header className="app-text-body-sm mb-3 flex items-center justify-between border-l-4 border-app-accent pl-2 font-semibold text-app-ink">
        <span>{group.name_ko}</span>
        <span className="app-text-caption font-normal text-app-ink/55">
          {group.parts.length}개
        </span>
      </header>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
        {group.parts.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onOpen(p.id)}
            className="group relative flex flex-col items-start rounded-xl border border-app-border bg-app-surface-raised p-3 text-left transition-colors hover:border-app-accent hover:bg-app-surface-hover"
          >
            <CountBadge count={p.count} />
            <div className="app-text-body-sm mt-2 font-semibold text-app-ink">
              {p.name_ko}
            </div>
            {p.name_en ? (
              <div className="app-text-caption text-app-ink/55">{p.name_en}</div>
            ) : null}
          </button>
        ))}
      </div>
    </section>
  );
}

function RegionCard({
  region,
  onClick,
}: {
  region: RegionOut;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative flex flex-col items-start rounded-xl border border-app-border bg-app-surface p-3 text-left transition-colors hover:border-app-accent hover:bg-app-surface-hover"
    >
      <CountBadge count={region.count} />
      <div className="mt-1 text-2xl">{region.flag}</div>
      <div className="app-text-body-sm font-semibold text-app-ink">
        {region.name_ko}
      </div>
      {region.name_en ? (
        <div className="app-text-caption text-app-ink/55">{region.name_en}</div>
      ) : null}
    </button>
  );
}

function TypeCard({ type, onClick }: { type: TypeOut; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative flex flex-col items-start rounded-xl border border-app-border bg-app-surface p-3 text-left transition-colors hover:border-app-accent hover:bg-app-surface-hover"
    >
      <CountBadge count={type.count} />
      <div className="app-text-body-sm mt-2 font-semibold text-app-ink">
        {type.name_ko}
      </div>
      {type.desc ? (
        <div className="app-text-caption mt-1 text-app-ink/55 line-clamp-2">
          {type.desc}
        </div>
      ) : null}
    </button>
  );
}

function CompetitorCard({
  competitor,
  onClick,
}: {
  competitor: CompetitorOut;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative flex flex-col items-start rounded-xl border border-app-border bg-app-surface p-3 text-left transition-colors hover:border-app-accent hover:bg-app-surface-hover"
    >
      <CountBadge count={competitor.count} />
      <div className="mt-1 text-2xl">{competitor.flag}</div>
      <div className="app-text-body-sm font-semibold text-app-ink">
        {competitor.name_ko}
      </div>
      {competitor.name_en ? (
        <div className="app-text-caption text-app-ink/55">{competitor.name_en}</div>
      ) : null}
      {competitor.note ? (
        <div className="app-text-caption mt-1 text-app-ink/45 line-clamp-2">
          {competitor.note}
        </div>
      ) : null}
    </button>
  );
}

function CountBadge({ count }: { count: number }) {
  return (
    <span
      className={cn(
        'absolute right-2 top-2 rounded-full px-2 py-0.5 app-text-caption',
        count === 0
          ? 'bg-app-bg text-app-ink/45'
          : 'bg-app-accent/15 text-app-accent',
      )}
    >
      {count}건
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────
// DetailSection — table view
// ─────────────────────────────────────────────────────────────────

interface DetailSectionProps {
  detail: Detail;
  loading: boolean;
  isAdmin: boolean;
  onShowHistory: (it: LawItemOut) => void;
  onAdd: () => void;
  onEdit: (id: string) => void;
  onDelete: (id: string, name: string) => void;
}

function DetailSection({
  detail,
  loading,
  isAdmin,
  onShowHistory,
  onAdd,
  onEdit,
  onDelete,
}: DetailSectionProps) {
  const { t } = useTranslation('apps');

  if (loading) return <LoadingBlock />;

  if (detail.kind === 'search') {
    return (
      <ItemsTable
        view="types"
        items={detail.items}
        isAdmin={false}
        onShowHistory={onShowHistory}
        onEdit={onEdit}
        onDelete={onDelete}
        countText={t('ai.lawSearch.totalCount', { count: detail.items.length })}
      />
    );
  }

  if (detail.kind === 'competitor') {
    const data = detail.data;
    if (!data) return null;
    return (
      <div className="space-y-3">
        <header className="flex items-center justify-between gap-2">
          <span className="app-text-caption text-app-ink/55">
            {t('ai.lawSearch.totalCount', { count: data.items.length })}
          </span>
        </header>
        <CompetitorSpecsTable items={data.items} />
      </div>
    );
  }

  const data = detail.data;
  if (!data) return null;
  return (
    <div className="space-y-3">
      <header className="flex items-center justify-between gap-2">
        <span className="app-text-caption text-app-ink/55">
          {t('ai.lawSearch.totalCount', { count: data.items.length })}
        </span>
        {isAdmin ? (
          <Button variant="primary" onClick={onAdd}>
            <Plus size={14} />
            {t('ai.lawSearch.actions.add')}
          </Button>
        ) : null}
      </header>
      <ItemsTable
        view={detail.kind === 'part' ? 'parts' : detail.kind === 'region' ? 'regions' : 'types'}
        items={data.items}
        isAdmin={isAdmin}
        onShowHistory={onShowHistory}
        onEdit={onEdit}
        onDelete={onDelete}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Items table — column set depends on entry tab (parts/regions/types)
// ─────────────────────────────────────────────────────────────────

interface ItemsTableProps {
  view: 'parts' | 'regions' | 'types';
  items: LawItemOut[];
  isAdmin: boolean;
  onShowHistory: (it: LawItemOut) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string, name: string) => void;
  countText?: string;
}

function ItemsTable({
  view,
  items,
  isAdmin,
  onShowHistory,
  onEdit,
  onDelete,
  countText,
}: ItemsTableProps) {
  const { t } = useTranslation('apps');
  if (!items.length) {
    return <EmptyState title={t('ai.lawSearch.empty.items')} />;
  }

  const cols: { id: string; label: string; className?: string }[] = (() => {
    if (view === 'parts') {
      return [
        { id: 'no', label: t('ai.lawSearch.cols.no'), className: 'w-10' },
        { id: 'name', label: t('ai.lawSearch.cols.name'), className: 'w-[22%]' },
        { id: 'regions', label: t('ai.lawSearch.cols.regions'), className: 'w-[12%]' },
        { id: 'desc', label: t('ai.lawSearch.cols.description') },
        { id: 'caution', label: t('ai.lawSearch.cols.caution'), className: 'w-[14%]' },
        { id: 'date', label: t('ai.lawSearch.cols.dates'), className: 'w-[10%]' },
        { id: 'src', label: t('ai.lawSearch.cols.source'), className: 'w-12' },
        { id: 'note', label: t('ai.lawSearch.cols.note'), className: 'w-[14%]' },
      ];
    }
    if (view === 'regions') {
      return [
        { id: 'no', label: t('ai.lawSearch.cols.no'), className: 'w-10' },
        { id: 'parts', label: t('ai.lawSearch.cols.parts'), className: 'w-[12%]' },
        { id: 'name', label: t('ai.lawSearch.cols.name'), className: 'w-[22%]' },
        { id: 'desc', label: t('ai.lawSearch.cols.description') },
        { id: 'caution', label: t('ai.lawSearch.cols.caution'), className: 'w-[14%]' },
        { id: 'date', label: t('ai.lawSearch.cols.dates'), className: 'w-[10%]' },
        { id: 'src', label: t('ai.lawSearch.cols.source'), className: 'w-12' },
        { id: 'note', label: t('ai.lawSearch.cols.note'), className: 'w-[14%]' },
      ];
    }
    return [
      { id: 'no', label: t('ai.lawSearch.cols.no'), className: 'w-10' },
      { id: 'name', label: t('ai.lawSearch.cols.name'), className: 'w-[22%]' },
      { id: 'parts', label: t('ai.lawSearch.cols.parts'), className: 'w-[10%]' },
      { id: 'regions', label: t('ai.lawSearch.cols.regions'), className: 'w-[10%]' },
      { id: 'desc', label: t('ai.lawSearch.cols.description') },
      { id: 'caution', label: t('ai.lawSearch.cols.caution'), className: 'w-[12%]' },
      { id: 'date', label: t('ai.lawSearch.cols.dates'), className: 'w-[10%]' },
      { id: 'src', label: t('ai.lawSearch.cols.source'), className: 'w-12' },
      { id: 'note', label: t('ai.lawSearch.cols.note'), className: 'w-[12%]' },
    ];
  })();

  return (
    <div className="overflow-x-auto rounded-xl border border-app-border bg-app-surface">
      <table className="w-full min-w-[1100px] border-collapse">
        <thead>
          <tr className="border-b border-app-border bg-app-bg/60">
            {cols.map((c) => (
              <th
                key={c.id}
                className={cn(
                  'app-text-caption px-2 py-2 text-left font-medium text-app-ink/65',
                  c.className,
                )}
              >
                {c.label}
              </th>
            ))}
            {isAdmin ? (
              <th className="app-text-caption w-24 px-2 py-2 font-medium text-app-ink/65">
                {t('ai.lawSearch.cols.actions')}
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {items.map((it, idx) => (
            <tr
              key={it.id}
              className="border-b border-b-app-border [border-bottom-style:dashed]"
            >
              {cols.map((c) => (
                <td
                  key={c.id}
                  className="app-text-body-sm px-2 py-2 align-top text-app-ink"
                >
                  {renderCell(c.id, it, idx, onShowHistory, t)}
                </td>
              ))}
              {isAdmin ? (
                <td className="px-2 py-2 align-top">
                  <div className="flex items-center gap-1">
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => onEdit(it.id)}
                      aria-label={String(t('ai.lawSearch.actions.edit'))}
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      onClick={() => onDelete(it.id, it.name)}
                      aria-label={String(t('ai.lawSearch.actions.delete'))}
                      className="text-ui-danger hover:text-ui-danger"
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderCell(
  colId: string,
  it: LawItemOut,
  idx: number,
  onShowHistory: (it: LawItemOut) => void,
  t: AppsT,
): React.ReactNode {
  switch (colId) {
    case 'no':
      return <span className="tabular-nums">{idx + 1}</span>;
    case 'name': {
      const hasHistory = (it.history?.length ?? 0) > 0;
      return (
        <div>
          <button
            type="button"
            onClick={() => onShowHistory(it)}
            className="inline-flex items-start gap-1 text-left font-semibold text-app-ink underline-offset-4 hover:underline"
            title={t('ai.lawSearch.history.title')}
          >
            <span>{it.name}</span>
            {hasHistory ? (
              <span className="ml-1 inline-flex items-center gap-0.5 rounded bg-app-accent/15 px-1 app-text-caption text-app-accent">
                <History size={10} />
                {it.history?.length}
              </span>
            ) : null}
          </button>
          {it.name_en ? (
            <div className="app-text-caption text-app-ink/55">{it.name_en}</div>
          ) : null}
        </div>
      );
    }
    case 'parts':
      return (
        <div className="flex flex-wrap gap-1">
          {(it.parts ?? []).map((p) => (
            <Badge key={p.id} tone="neutral">
              {p.name_ko}
            </Badge>
          ))}
        </div>
      );
    case 'regions':
      return (
        <div className="flex flex-wrap gap-1">
          {(it.regions ?? []).map((r) => (
            <Badge key={r.id} tone="accent">
              {r.name_ko}
            </Badge>
          ))}
        </div>
      );
    case 'desc':
      return <div className="whitespace-pre-wrap">{it.description ?? ''}</div>;
    case 'caution':
      return <div className="whitespace-pre-wrap text-app-ink/65">{it.caution ?? ''}</div>;
    case 'date':
      return (
        <div>
          <div className="tabular-nums">{it.effective_date || '—'}</div>
          {it.revision_date && it.revision_date !== it.effective_date ? (
            <div className="app-text-caption text-app-ink/55">
              {t('ai.lawSearch.revisionDate', { date: it.revision_date })}
            </div>
          ) : null}
        </div>
      );
    case 'src': {
      return <SourceUrlLink sourceUrl={it.source_url} />;
    }
    case 'note':
      return <div className="whitespace-pre-wrap text-app-ink/65">{it.note ?? ''}</div>;
    default:
      return null;
  }
}

// ─────────────────────────────────────────────────────────────────
// Competitor specs table (no admin actions; different cols)
// ─────────────────────────────────────────────────────────────────

function CompetitorSpecsTable({ items }: { items: CompetitorSpecOut[] }) {
  const { t } = useTranslation('apps');
  if (!items.length) {
    return <EmptyState title={t('ai.lawSearch.empty.items')} />;
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-app-border bg-app-surface">
      <table className="w-full min-w-[1000px] border-collapse">
        <thead>
          <tr className="border-b border-app-border bg-app-bg/60">
            <th className="app-text-caption w-10 px-2 py-2 text-left font-medium text-app-ink/65">
              No.
            </th>
            <th className="app-text-caption w-[22%] px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.specName')}
            </th>
            <th className="app-text-caption w-[10%] px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.category')}
            </th>
            <th className="app-text-caption w-[12%] px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.parts')}
            </th>
            <th className="app-text-caption px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.description')}
            </th>
            <th className="app-text-caption w-[14%] px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.caution')}
            </th>
            <th className="app-text-caption w-12 px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.source')}
            </th>
            <th className="app-text-caption w-[12%] px-2 py-2 text-left font-medium text-app-ink/65">
              {t('ai.lawSearch.cols.note')}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((s, idx) => (
            <tr
              key={s.id}
              className="border-b border-b-app-border [border-bottom-style:dashed]"
            >
              <td className="app-text-body-sm px-2 py-2 align-top tabular-nums text-app-ink">
                {idx + 1}
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink">
                <div className="font-semibold">{s.name}</div>
                {s.name_en ? (
                  <div className="app-text-caption text-app-ink/55">{s.name_en}</div>
                ) : null}
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink">
                {s.category ? <Badge tone="accent">{s.category}</Badge> : '—'}
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink">
                <div className="flex flex-wrap gap-1">
                  {(s.parts ?? []).map((p) => (
                    <Badge key={p.id} tone="neutral">
                      {p.name_ko}
                    </Badge>
                  ))}
                </div>
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink">
                <div className="whitespace-pre-wrap">{s.description ?? ''}</div>
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink/65">
                <div className="whitespace-pre-wrap">{s.caution ?? ''}</div>
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink">
                <SourceUrlLink sourceUrl={s.source_url} />
              </td>
              <td className="app-text-body-sm px-2 py-2 align-top text-app-ink/65">
                <div className="whitespace-pre-wrap">{s.note ?? ''}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// History dialog
// ─────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<string, { labelKey: string; tone: 'success' | 'neutral' | 'warning' | 'accent' }> = {
  current: { labelKey: 'ai.lawSearch.history.status.current', tone: 'success' },
  previous: { labelKey: 'ai.lawSearch.history.status.previous', tone: 'neutral' },
  draft: { labelKey: 'ai.lawSearch.history.status.draft', tone: 'warning' },
  upcoming: { labelKey: 'ai.lawSearch.history.status.upcoming', tone: 'accent' },
};

function HistoryDialog({
  item,
  onClose,
}: {
  item: LawItemOut | null;
  onClose: () => void;
}) {
  const { t } = useTranslation('apps');
  return (
    <Dialog
      open={item !== null}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      title={
        item
          ? t('ai.lawSearch.history.titleWithName', { name: item.name })
          : t('ai.lawSearch.history.title')
      }
      maxWidth="max-w-3xl"
    >
      {item && (item.history?.length ?? 0) > 0 ? (
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-app-border">
              <th className="app-text-caption w-[24%] px-2 py-2 text-left text-app-ink/65">
                {t('ai.lawSearch.history.version')}
              </th>
              <th className="app-text-caption w-[12%] px-2 py-2 text-left text-app-ink/65">
                {t('ai.lawSearch.history.statusLabel')}
              </th>
              <th className="app-text-caption w-[14%] px-2 py-2 text-left text-app-ink/65">
                {t('ai.lawSearch.history.date')}
              </th>
              <th className="app-text-caption px-2 py-2 text-left text-app-ink/65">
                {t('ai.lawSearch.history.summary')}
              </th>
            </tr>
          </thead>
          <tbody>
            {item.history?.map((h: HistoryEntry, i) => {
              const meta = STATUS_LABEL[h.status] ?? { labelKey: h.status, tone: 'neutral' as const };
              return (
                <tr key={i} className="border-b border-b-app-border [border-bottom-style:dashed]">
                  <td className="app-text-body-sm px-2 py-2 align-top font-semibold text-app-ink">
                    {h.version || '—'}
                  </td>
                  <td className="px-2 py-2 align-top">
                    <Badge tone={meta.tone}>
                      {meta.labelKey.startsWith('ai.') ? t(meta.labelKey) : meta.labelKey}
                    </Badge>
                  </td>
                  <td className="app-text-body-sm px-2 py-2 align-top tabular-nums text-app-ink">
                    {h.date || '—'}
                  </td>
                  <td className="app-text-body-sm px-2 py-2 align-top text-app-ink">
                    {h.summary || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <EmptyState title={t('ai.lawSearch.history.empty')} />
      )}
    </Dialog>
  );
}

// ─────────────────────────────────────────────────────────────────
// Item edit dialog (admin)
// ─────────────────────────────────────────────────────────────────

function ItemEditDialog({
  mode,
  item,
  parts,
  regions,
  types,
  context,
  workspaceSlug,
  onCancel,
  onSaved,
}: {
  mode: 'create' | 'edit';
  item: LawItemRaw | null;
  parts: PartsResponse | null;
  regions: RegionsResponse | null;
  types: TypesResponse | null;
  context: Detail | null;
  workspaceSlug: string | null;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const { token } = useAuth();
  const { t } = useTranslation('apps');
  const toast = useToast();

  const flatParts = useMemo(
    () => (parts?.groups ?? []).flatMap((g) => g.parts),
    [parts],
  );
  const allRegions = regions?.regions ?? [];
  const allTypes = (types?.types ?? []).filter((t) => !t.is_virtual);

  const initial = useMemo<LawItemWriteIn>(() => {
    if (item) {
      return {
        name: item.name,
        name_en: item.name_en ?? '',
        type: item.type,
        part_ids: item.part_ids,
        region_ids: item.region_ids,
        description: item.description ?? '',
        caution: item.caution ?? '',
        effective_date: item.effective_date ?? '',
        revision_date: item.revision_date ?? '',
        source_url: item.source_url ?? '',
        note: item.note ?? '',
        history: item.history ?? [],
      };
    }
    // create defaults — preset by context
    const preset: LawItemWriteIn = {
      name: '',
      name_en: '',
      type: '',
      part_ids: [],
      region_ids: [],
      description: '',
      caution: '',
      effective_date: '',
      revision_date: '',
      source_url: '',
      note: '',
      history: [],
    };
    if (context?.kind === 'part') preset.part_ids = [context.id];
    if (context?.kind === 'region') preset.region_ids = [context.id];
    if (context?.kind === 'type') preset.type = context.id;
    return preset;
  }, [item, context]);

  const [form, setForm] = useState<LawItemWriteIn>(initial);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  function togglePart(id: string) {
    setForm((f) => ({
      ...f,
      part_ids: f.part_ids.includes(id)
        ? f.part_ids.filter((x) => x !== id)
        : [...f.part_ids, id],
    }));
  }

  function toggleRegion(id: string) {
    setForm((f) => ({
      ...f,
      region_ids: f.region_ids.includes(id)
        ? f.region_ids.filter((x) => x !== id)
        : [...f.region_ids, id],
    }));
  }

  async function save() {
    if (!workspaceSlug) return;
    setSaving(true);
    setErrors([]);
    try {
      if (mode === 'create') {
        await createItem(token, workspaceSlug, form);
        toast.success(t('ai.lawSearch.save.created'));
      } else if (item) {
        await updateItem(token, workspaceSlug, item.id, form);
        toast.success(t('ai.lawSearch.save.updated'));
      }
      onSaved();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // Try extract details list from ApiRequestError payload
      const payload =
        e && typeof e === 'object' && 'payload' in e
          ? ((e as { payload?: unknown }).payload as
              | { detail?: { params?: { details?: string[] } } }
              | null
              | undefined)
          : null;
      const details = payload?.detail?.params?.details;
      if (details?.length) setErrors(details);
      else setErrors([msg]);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(o) => {
        if (!o) onCancel();
      }}
      title={mode === 'create' ? t('ai.lawSearch.edit.titleCreate') : t('ai.lawSearch.edit.titleEdit')}
      maxWidth="max-w-3xl"
      dismissOnInteractOutside={false}
      actions={
        <>
          <Button variant="ghost" onClick={onCancel}>
            {t('ai.lawSearch.actions.cancel')}
          </Button>
          <Button variant="primary" onClick={save} disabled={saving}>
            {saving ? <Loader2 size={14} className="animate-spin" /> : null}
            {t('ai.lawSearch.actions.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={t('ai.lawSearch.fields.name')} required>
          <Input
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </Field>
        <Field label={t('ai.lawSearch.fields.nameEn')}>
          <Input
            value={form.name_en ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, name_en: e.target.value }))}
          />
        </Field>

        <div className="grid grid-cols-3 gap-3">
          <Field label={t('ai.lawSearch.fields.type')} required>
            <select
              className={SELECT_CLS}
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
            >
              <option value="">{t('ai.lawSearch.selectPlaceholder')}</option>
              {allTypes.map((t2) => (
                <option key={t2.id} value={t2.id}>
                  {t2.name_ko}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t('ai.lawSearch.fields.effectiveDate')}>
            <Input
              type="date"
              value={form.effective_date ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, effective_date: e.target.value }))}
            />
          </Field>
          <Field label={t('ai.lawSearch.fields.revisionDate')}>
            <Input
              type="date"
              value={form.revision_date ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, revision_date: e.target.value }))}
            />
          </Field>
        </div>

        <Field label={t('ai.lawSearch.fields.parts')}>
          <CheckGrid
            items={flatParts.map((p) => ({ id: p.id, label: p.name_ko }))}
            selected={form.part_ids}
            onToggle={togglePart}
          />
        </Field>

        <Field label={t('ai.lawSearch.fields.regions')}>
          <CheckGrid
            items={allRegions.map((r) => ({ id: r.id, label: `${r.flag ?? ''} ${r.name_ko}` }))}
            selected={form.region_ids}
            onToggle={toggleRegion}
          />
        </Field>

        <Field label={t('ai.lawSearch.fields.description')}>
          <textarea
            rows={4}
            className={TEXTAREA_CLS}
            value={form.description ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
        </Field>

        <Field label={t('ai.lawSearch.fields.caution')}>
          <textarea
            rows={2}
            className={TEXTAREA_CLS}
            value={form.caution ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, caution: e.target.value }))}
          />
        </Field>

        <Field label={t('ai.lawSearch.fields.sourceUrl')}>
          <Input
            type="url"
            value={form.source_url ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, source_url: e.target.value }))}
          />
        </Field>

        <Field label={t('ai.lawSearch.fields.note')}>
          <Input
            value={form.note ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
          />
        </Field>

        {errors.length ? (
          <InlineNotice tone="danger">
            <ul className="list-disc pl-5">
              {errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </InlineNotice>
        ) : null}
      </div>
    </Dialog>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="app-text-caption mb-1 font-medium text-app-ink">
        {label}
        {required ? <span className="ml-1 text-ui-danger">*</span> : null}
      </div>
      {children}
    </label>
  );
}

function CheckGrid({
  items,
  selected,
  onToggle,
}: {
  items: { id: string; label: string }[];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-1 rounded-md border border-app-border bg-app-surface p-2 lg:grid-cols-4">
      {items.map((it) => {
        const isOn = selected.includes(it.id);
        return (
          <label
            key={it.id}
            className={cn(
              'app-text-control-sm flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 transition-colors hover:bg-app-surface-hover',
              isOn && 'bg-app-accent/15 text-app-accent',
            )}
          >
            <input
              type="checkbox"
              className="accent-app-accent"
              checked={isOn}
              onChange={() => onToggle(it.id)}
            />
            <span>{it.label}</span>
          </label>
        );
      })}
    </div>
  );
}

const SELECT_CLS = 'app-field-input';
const TEXTAREA_CLS =
  'w-full rounded-md border border-app-border bg-app-surface px-3 py-2 app-text-control-sm text-app-ink outline-none focus:border-app-accent';

function LoadingBlock() {
  return (
    <div className="flex h-40 items-center justify-center text-app-accent">
      <Loader2 size={22} className="animate-spin" />
    </div>
  );
}
