import { useCallback, useEffect, useState } from 'react';

import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import {
  AlertCircle,
  Download,
  ExternalLink,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';
import {
  deletePptJob,
  downloadPptx,
  listPptJobs,
  PptGeneratorApiError,
  type PptJobListItem,
} from '../api/ppt-generator-api';
import { buildPptDownloadFilename } from './ppt-generator/download-filename';
import {
  buildPptAssistantJobPath,
  buildPptAssistantPath,
} from '../ppt-assistant-paths';

const STATUS_CLASS: Record<PptJobListItem['status'], string> = {
  pending: 'border-app-border bg-app-surface-sidebar text-app-ink/60',
  running: 'border-app-accent/30 bg-app-accent/10 text-app-accent',
  completed:
    'border-app-success-border bg-app-success-bg text-app-success-text',
  error: 'border-app-danger-border bg-app-danger-bg text-app-danger-text',
  cancelled: 'border-app-border bg-app-surface-sidebar text-app-ink/45',
};

export function PptHistoryView({ appId }: { appId: string }) {
  const { t } = useTranslation('apps');
  const navigate = useNavigate();
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);

  const [items, setItems] = useState<PptJobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyJobIds, setBusyJobIds] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const jobPath = useCallback(
    (jobId: string) =>
      workspaceSlug
        ? buildPptAssistantJobPath(appId, workspaceSlug, jobId)
        : '/',
    [appId, workspaceSlug],
  );

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await listPptJobs({ token, workspaceSlug, limit: 50 });
      setItems(response.items);
      setSelectedIds(new Set());
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.history.errors.load'),
      );
    } finally {
      setLoading(false);
    }
  }, [t, token, workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const markBusy = (jobId: string, busy: boolean) => {
    setBusyJobIds((prev) => {
      const next = new Set(prev);
      if (busy) {
        next.add(jobId);
      } else {
        next.delete(jobId);
      }
      return next;
    });
  };

  const openNew = () => {
    if (!workspaceSlug) return;
    navigate(buildPptAssistantPath(appId, workspaceSlug));
  };

  const openJob = (jobId: string) => {
    navigate(jobPath(jobId));
  };

  const handleDownload = async (item: PptJobListItem) => {
    if (!token || !item.pptx_ready) return;
    markBusy(item.job_id, true);
    setError(null);
    try {
      await downloadPptx({
        token,
        workspaceSlug,
        jobId: item.job_id,
        filename: buildPptDownloadFilename(item.title ?? '', item.job_id),
      });
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.errors.download'),
      );
    } finally {
      markBusy(item.job_id, false);
    }
  };

  const handleDelete = async (item: PptJobListItem) => {
    if (!token) return;
    if (!window.confirm(t('ai.pptGenerator.history.confirmDelete'))) return;
    markBusy(item.job_id, true);
    setError(null);
    try {
      await deletePptJob({ token, workspaceSlug, jobId: item.job_id });
      setItems((prev) => prev.filter((row) => row.job_id !== item.job_id));
      // 선택 상태에서도 제거 — 안 그러면 선택 카운트/전체선택 표시가 어긋나고
      // 삭제된 ID 가 selectedIds 에 잔존한다(bulk 삭제 경로와 동일하게 정리).
      setSelectedIds((prev) => {
        if (!prev.has(item.job_id)) return prev;
        const next = new Set(prev);
        next.delete(item.job_id);
        return next;
      });
    } catch (e) {
      setError(
        e instanceof PptGeneratorApiError
          ? e.message
          : t('ai.pptGenerator.history.errors.delete'),
      );
    } finally {
      markBusy(item.job_id, false);
    }
  };

  const toggleOne = (jobId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  };

  const allSelected = items.length > 0 && selectedIds.size === items.length;

  const toggleAll = () => {
    setSelectedIds(() =>
      allSelected ? new Set() : new Set(items.map((row) => row.job_id)),
    );
  };

  const clearSelection = () => setSelectedIds(new Set());

  const anyBusy = busyJobIds.size > 0;
  const selectedDownloadable = items.filter(
    (row) => selectedIds.has(row.job_id) && row.pptx_ready,
  ).length;

  const handleBulkDownload = async () => {
    if (!token) return;
    const targets = items.filter(
      (row) => selectedIds.has(row.job_id) && row.pptx_ready,
    );
    setError(null);
    for (const item of targets) {
      markBusy(item.job_id, true);
      try {
        await downloadPptx({
          token,
          workspaceSlug,
          jobId: item.job_id,
          filename: buildPptDownloadFilename(item.title ?? '', item.job_id),
        });
      } catch (e) {
        setError(
          e instanceof PptGeneratorApiError
            ? e.message
            : t('ai.pptGenerator.errors.download'),
        );
      } finally {
        markBusy(item.job_id, false);
      }
    }
  };

  const handleBulkDelete = async () => {
    if (!token) return;
    const targets = items.filter((row) => selectedIds.has(row.job_id));
    if (targets.length === 0) return;
    if (
      !window.confirm(
        t('ai.pptGenerator.history.confirmBulkDelete', {
          count: targets.length,
        }),
      )
    )
      return;
    setError(null);
    const deleted: string[] = [];
    for (const item of targets) {
      markBusy(item.job_id, true);
      try {
        await deletePptJob({ token, workspaceSlug, jobId: item.job_id });
        deleted.push(item.job_id);
      } catch (e) {
        setError(
          e instanceof PptGeneratorApiError
            ? e.message
            : t('ai.pptGenerator.history.errors.delete'),
        );
      } finally {
        markBusy(item.job_id, false);
      }
    }
    if (deleted.length) {
      const deletedSet = new Set(deleted);
      setItems((prev) => prev.filter((row) => !deletedSet.has(row.job_id)));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        deletedSet.forEach((id) => next.delete(id));
        return next;
      });
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-app-bg text-app-ink">
      <header className="flex items-center gap-3 border-b border-app-border bg-app-bg px-8 pb-4 pt-6">
        <div className="flex size-9 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-accent">
          <History className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h1 className="app-text-title-lg text-app-ink">
            {t('ai.pptGenerator.history.title')}
          </h1>
          <p className="app-text-body mt-1 text-app-ink/55">
            {t('ai.pptGenerator.history.subtitle')}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="app-control h-8 px-3"
          >
            <RefreshCw className="h-4 w-4" />
            {t('ai.pptGenerator.history.refresh')}
          </button>
          <button
            type="button"
            onClick={openNew}
            className="app-control-primary h-8 px-3"
          >
            <Plus className="h-4 w-4" />
            {t('ai.pptGenerator.history.newPpt')}
          </button>
        </div>
      </header>

      {error ? (
        <div className="app-text-body-sm flex items-center gap-2 border-b border-app-danger-border bg-app-danger-bg px-8 py-2 text-app-danger-text">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      ) : null}

      <div className="custom-scrollbar min-h-0 flex-1 overflow-auto px-8 py-6">
        {loading ? (
          <div className="flex h-full items-center justify-center gap-2 text-app-ink/55">
            <Loader2 className="h-5 w-5 animate-spin text-app-accent" />
            <span className="app-text-body-sm">
              {t('ai.pptGenerator.history.loading')}
            </span>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <History className="h-8 w-8 text-app-ink/30" />
            <div>
              <p className="app-text-body-sm font-medium text-app-ink">
                {t('ai.pptGenerator.history.emptyTitle')}
              </p>
              <p className="app-text-caption mt-1 text-app-ink/45">
                {t('ai.pptGenerator.history.emptyDescription')}
              </p>
            </div>
            <button
              type="button"
              onClick={openNew}
              className="app-control-primary h-8 px-3"
            >
              <Plus className="h-4 w-4" />
              {t('ai.pptGenerator.history.newPpt')}
            </button>
          </div>
        ) : (
          <div className="min-w-[796px]">
            {selectedIds.size > 0 ? (
              <div className="mb-3 flex items-center gap-2 rounded-lg border border-app-accent/30 bg-app-accent/5 px-3 py-2">
                <span className="app-text-body-sm font-medium text-app-ink">
                  {t('ai.pptGenerator.history.selected', {
                    count: selectedIds.size,
                  })}
                </span>
                <button
                  type="button"
                  onClick={() => void handleBulkDownload()}
                  disabled={selectedDownloadable === 0 || anyBusy}
                  className="app-control ml-2 h-8 px-3"
                >
                  <Download className="h-4 w-4" />
                  {t('ai.pptGenerator.history.downloadSelected')}
                </button>
                <button
                  type="button"
                  onClick={() => void handleBulkDelete()}
                  disabled={anyBusy}
                  className="app-control h-8 px-3 text-app-danger-text hover:text-app-danger-text"
                >
                  <Trash2 className="h-4 w-4" />
                  {t('ai.pptGenerator.history.deleteSelected')}
                </button>
                <button
                  type="button"
                  onClick={clearSelection}
                  className="app-control-ghost ml-auto h-8 px-2"
                >
                  {t('ai.pptGenerator.history.clearSelection')}
                </button>
              </div>
            ) : null}
            <div className="grid grid-cols-[36px_minmax(220px,1fr)_120px_100px_150px_110px_160px] border-b border-app-border px-2 py-2">
              <span className="flex items-center">
                <input
                  type="checkbox"
                  className="size-4 cursor-pointer accent-app-accent"
                  checked={allSelected}
                  onChange={toggleAll}
                  aria-label={t('ai.pptGenerator.history.selectAll')}
                />
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.title')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.status')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.template')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.createdAt')}
              </span>
              <span className="app-text-overline text-app-ink/40">
                {t('ai.pptGenerator.history.columns.slides')}
              </span>
              <span className="app-text-overline text-right text-app-ink/40">
                {t('ai.pptGenerator.history.columns.actions')}
              </span>
            </div>
            {items.map((item) => {
              const busy = busyJobIds.has(item.job_id);
              return (
                <div
                  key={item.job_id}
                  className={cn(
                    'grid grid-cols-[36px_minmax(220px,1fr)_120px_100px_150px_110px_160px] items-center border-b border-app-border px-2 py-3 transition-colors hover:bg-app-surface-hover',
                    selectedIds.has(item.job_id) && 'bg-app-accent/5',
                  )}
                >
                  <span className="flex items-center">
                    <input
                      type="checkbox"
                      className="size-4 cursor-pointer accent-app-accent"
                      checked={selectedIds.has(item.job_id)}
                      onChange={() => toggleOne(item.job_id)}
                      aria-label={t('ai.pptGenerator.history.selectRow')}
                    />
                  </span>
                  <button
                    type="button"
                    onClick={() => openJob(item.job_id)}
                    className="min-w-0 text-left"
                  >
                    <span className="app-text-body-sm block truncate font-medium text-app-ink hover:text-app-accent">
                      {item.title || t('ai.pptGenerator.history.untitled')}
                    </span>
                    <span className="app-text-caption mt-0.5 block truncate text-app-ink/40">
                      {item.job_id}
                    </span>
                  </button>
                  <span
                    className={cn(
                      'app-text-caption inline-flex w-fit items-center rounded-full border px-2 py-0.5 font-medium',
                      STATUS_CLASS[item.status],
                    )}
                  >
                    {t(`ai.pptGenerator.history.status.${item.status}`)}
                  </span>
                  <span className="app-text-body-sm text-app-ink/60">
                    {item.aspect}
                  </span>
                  <span className="app-text-body-sm text-app-ink/60">
                    <UserDateTime value={item.created_at} />
                  </span>
                  <span className="app-text-body-sm text-app-ink/60">
                    {t('ai.pptGenerator.history.slideCount', {
                      count: item.n_slides,
                    })}
                  </span>
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => openJob(item.job_id)}
                      className="app-control-ghost h-8 px-2"
                    >
                      <ExternalLink className="h-4 w-4" />
                      {t('ai.pptGenerator.history.open')}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDownload(item)}
                      disabled={!item.pptx_ready || busy}
                      className="app-control-ghost h-8 px-2"
                      title={
                        item.pptx_ready
                          ? t('ai.pptGenerator.result.downloadPptx')
                          : t('ai.pptGenerator.history.notReady')
                      }
                    >
                      {busy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(item)}
                      disabled={busy}
                      className="app-control-ghost h-8 px-2 text-app-danger-text hover:text-app-danger-text"
                      title={t('ai.pptGenerator.history.delete')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
