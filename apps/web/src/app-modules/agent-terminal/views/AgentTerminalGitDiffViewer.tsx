import { Badge, Button, Dialog, EmptyState } from '@open-work-hub/ui';
import {
  ChevronDown,
  ChevronRight,
  FileDiff,
  Maximize2,
  RefreshCw,
  X,
} from 'lucide-react';
import { lazy, Suspense, useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AgentTerminalGitChange } from '../api/agent-terminal-api';

const AgentTerminalDiffSurface = lazy(() =>
  import('./AgentTerminalDiffSurface').then((module) => ({
    default: module.AgentTerminalDiffSurface,
  })),
);

type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger';

export interface AgentTerminalGitDiffSelection {
  badgeLabel: string;
  badgeTone: BadgeTone;
  contextLabel: string;
  key: string;
  kind: AgentTerminalGitChange['kind'];
  oldPath?: string | null;
  path: string;
}

export interface AgentTerminalGitDiffPayload {
  is_binary: boolean;
  new_content?: string | null;
  old_content?: string | null;
  too_large: boolean;
}

function DiffSurface({
  diff,
  selection,
}: {
  diff: AgentTerminalGitDiffPayload;
  selection: AgentTerminalGitDiffSelection;
}) {
  const { t } = useTranslation('apps');
  return (
    <Suspense
      fallback={
        <div className="grid h-full place-items-center text-app-ink/45">
          <FileDiff aria-hidden="true" className="size-5" />
          <span className="sr-only">{t('agentTerminal.git.diffLoading')}</span>
        </div>
      }
    >
      <AgentTerminalDiffSurface
        ariaLabel={t('agentTerminal.git.diffLabel', {
          path: selection.path,
        })}
        diffKey={selection.key}
        filePath={selection.path}
        kind={selection.kind}
        newContent={diff.new_content ?? ''}
        oldContent={diff.old_content ?? ''}
        oldPath={selection.oldPath}
      />
    </Suspense>
  );
}

export function AgentTerminalGitDiffViewer({
  diff,
  failed,
  loading,
  selection,
}: {
  diff: AgentTerminalGitDiffPayload | null;
  failed: boolean;
  loading: boolean;
  selection: AgentTerminalGitDiffSelection | null;
}) {
  const { t } = useTranslation('apps');
  const contentId = useId();
  const [open, setOpen] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const canRenderDiff = Boolean(diff && !diff.is_binary && !diff.too_large);

  useEffect(() => {
    setModalOpen(false);
  }, [selection?.key]);

  return (
    <section
      className={
        open
          ? 'flex min-h-[160px] flex-1 flex-col bg-app-bg'
          : 'shrink-0 bg-app-bg'
      }
    >
      <header className="flex shrink-0 items-center gap-1 border-b border-app-border bg-app-surface px-2 py-1.5">
        <button
          aria-controls={contentId}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 rounded px-1 py-1 text-left hover:bg-app-surface-hover"
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          {open ? (
            <ChevronDown aria-hidden="true" className="size-3.5 shrink-0" />
          ) : (
            <ChevronRight aria-hidden="true" className="size-3.5 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-xs font-semibold">
              {selection?.path ?? t('agentTerminal.git.diff.emptyTitle')}
            </p>
            {selection ? (
              <p className="mt-0.5 truncate app-text-caption text-app-ink/45">
                {selection.contextLabel}
              </p>
            ) : null}
          </div>
          {selection ? (
            <Badge tone={selection.badgeTone}>{selection.badgeLabel}</Badge>
          ) : null}
        </button>
        {canRenderDiff ? (
          <Button
            aria-label={t('agentTerminal.git.actions.expandDiff')}
            onClick={() => setModalOpen(true)}
            size="icon"
            title={t('agentTerminal.git.actions.expandDiff')}
            variant="ghost"
          >
            <Maximize2 aria-hidden="true" className="size-4" />
          </Button>
        ) : null}
      </header>

      {open ? (
        <div className="min-h-0 flex-1" id={contentId}>
          {loading && !diff ? (
            <div className="grid h-full place-items-center text-app-ink/45">
              <RefreshCw aria-hidden="true" className="size-5 animate-spin" />
              <span className="sr-only">
                {t('agentTerminal.git.diffLoading')}
              </span>
            </div>
          ) : failed ? (
            <div className="p-3">
              <EmptyState
                description={t('agentTerminal.git.diffFailedDescription')}
                title={t('agentTerminal.git.diffFailedTitle')}
              />
            </div>
          ) : diff?.is_binary ? (
            <div className="p-3">
              <EmptyState
                description={t('agentTerminal.git.binaryDescription')}
                title={t('agentTerminal.git.binaryTitle')}
              />
            </div>
          ) : diff?.too_large ? (
            <div className="p-3">
              <EmptyState
                description={t('agentTerminal.git.tooLargeDescription')}
                title={t('agentTerminal.git.tooLargeTitle')}
              />
            </div>
          ) : diff && selection ? (
            <DiffSurface diff={diff} selection={selection} />
          ) : (
            <div className="p-3">
              <EmptyState
                description={t('agentTerminal.git.diff.emptyDescription')}
                title={t('agentTerminal.git.diff.emptyTitle')}
              />
            </div>
          )}
        </div>
      ) : null}

      {selection && diff && canRenderDiff ? (
        <Dialog
          contentClassName="!h-[90dvh] !w-[90vw] !max-h-[90dvh] !max-w-none"
          description={selection.contextLabel}
          embedded
          layer="elevated"
          onOpenChange={setModalOpen}
          open={modalOpen}
          title={t('agentTerminal.git.expandedDiffTitle', {
            path: selection.path,
          })}
        >
          <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-app-border bg-app-surface px-4">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-app-ink">
                {selection.path}
              </h2>
              <p className="truncate app-text-caption text-app-ink/50">
                {selection.contextLabel}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge tone={selection.badgeTone}>{selection.badgeLabel}</Badge>
              <Button
                aria-label={t('agentTerminal.git.actions.closeExpandedDiff')}
                onClick={() => setModalOpen(false)}
                size="icon"
                title={t('agentTerminal.git.actions.closeExpandedDiff')}
                variant="ghost"
              >
                <X aria-hidden="true" className="size-4" />
              </Button>
            </div>
          </header>
          <div className="min-h-0 flex-1 bg-app-bg">
            <DiffSurface diff={diff} selection={selection} />
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
