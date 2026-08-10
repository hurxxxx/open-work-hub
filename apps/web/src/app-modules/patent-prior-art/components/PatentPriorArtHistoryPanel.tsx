import { useTranslation } from 'react-i18next';
import { RefreshCw, Square, Trash2 } from 'lucide-react';

import { Button } from '@open-alm/ui';

import { UserDateTime } from '@/src/components/date/UserDateTime';
import { cn } from '@/src/lib/utils';

import type { PatentPriorArtJob } from '../api/patent-prior-art-api';
import {
  type PatentPriorArtJobDisplayStatus,
  patentPriorArtJobDisplayStatus,
} from '../model/patent-prior-art-view-model';

const STATUS_CLASS: Record<PatentPriorArtJobDisplayStatus, string> = {
  cancelled: 'border-app-border bg-app-surface-sidebar text-app-ink/55',
  cleanup_pending:
    'border-app-warning-border bg-app-warning-bg text-app-warning-text',
  failed: 'border-app-danger-border bg-app-danger-bg text-app-danger-text',
  queued: 'border-app-border bg-app-surface-sidebar text-app-ink/65',
  retry_waiting:
    'border-app-warning-border bg-app-warning-bg text-app-warning-text',
  running: 'border-app-accent/30 bg-app-accent/10 text-app-accent',
  succeeded:
    'border-app-success-border bg-app-success-bg text-app-success-text',
};

export function PatentPriorArtHistoryPanel({
  activeJobId,
  busy,
  jobs,
  onCancel,
  onDelete,
  onRefresh,
  onSelect,
}: {
  activeJobId: string | null;
  busy: boolean;
  jobs: PatentPriorArtJob[];
  onCancel: (job: PatentPriorArtJob) => void;
  onDelete: (job: PatentPriorArtJob) => void;
  onRefresh: () => void;
  onSelect: (job: PatentPriorArtJob) => void;
}) {
  const { t } = useTranslation('apps');

  return (
    <aside
      aria-label={t('ai.patentPriorArt.history.ariaLabel')}
      className="min-h-0 rounded-xl border border-app-border bg-app-surface"
    >
      <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
        <div>
          <h2 className="app-text-title-sm">
            {t('ai.patentPriorArt.history.title')}
          </h2>
          <p className="mt-0.5 app-text-caption text-app-ink/55">
            {t('ai.patentPriorArt.history.count', { count: jobs.length })}
          </p>
        </div>
        <Button
          aria-label={t('ai.patentPriorArt.history.refresh')}
          disabled={busy}
          onClick={onRefresh}
          size="icon"
          variant="ghost"
        >
          <RefreshCw
            aria-hidden="true"
            className={cn(busy && 'animate-spin')}
            size={15}
          />
        </Button>
      </div>

      <div className="custom-scrollbar max-h-80 overflow-y-auto p-2 lg:max-h-[calc(100vh-12rem)]">
        {jobs.length === 0 ? (
          <p className="px-2 py-6 text-center app-text-body-sm text-app-ink/50">
            {t('ai.patentPriorArt.history.empty')}
          </p>
        ) : (
          <ul className="space-y-2">
            {jobs.map((job) => {
              const selected = activeJobId === job.id;
              const displayStatus = patentPriorArtJobDisplayStatus(job);
              return (
                <li
                  className={cn(
                    'rounded-lg border transition-colors',
                    selected
                      ? 'border-app-accent bg-app-accent/5'
                      : 'border-app-border hover:bg-app-surface-hover',
                  )}
                  key={job.id}
                >
                  <button
                    aria-current={selected ? 'true' : undefined}
                    className="block w-full px-3 pb-2 pt-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-app-accent"
                    onClick={() => onSelect(job)}
                    type="button"
                  >
                    <span className="block truncate app-text-control-sm font-semibold text-app-ink">
                      {job.title || t('ai.patentPriorArt.history.untitled')}
                    </span>
                    <span className="mt-1 flex flex-wrap items-center gap-1.5">
                      <span
                        className={cn(
                          'rounded-full border px-2 py-0.5 app-text-caption',
                          STATUS_CLASS[displayStatus],
                        )}
                      >
                        {t(`ai.patentPriorArt.status.${displayStatus}`)}
                      </span>
                      <UserDateTime
                        className="app-text-caption text-app-ink/45"
                        display="datetime"
                        value={job.created_at}
                      />
                    </span>
                  </button>
                  <div className="flex justify-end gap-1 border-t border-app-border/70 px-2 py-1.5">
                    {job.can_cancel ? (
                      <Button
                        disabled={busy}
                        onClick={() => onCancel(job)}
                        size="dense"
                        variant="ghost"
                      >
                        <Square aria-hidden="true" size={13} />
                        {t('ai.patentPriorArt.actions.cancel')}
                      </Button>
                    ) : null}
                    <Button
                      aria-label={t('ai.patentPriorArt.history.deleteLabel', {
                        title:
                          job.title || t('ai.patentPriorArt.history.untitled'),
                      })}
                      disabled={busy || job.status === 'running'}
                      onClick={() => onDelete(job)}
                      size="icon"
                      variant="ghost"
                    >
                      <Trash2 aria-hidden="true" size={14} />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
