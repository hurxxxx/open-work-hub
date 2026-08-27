import { History, Play, RefreshCw } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { AgentTerminalCodexThread } from '../api/agent-terminal-api';

export function AgentTerminalCodexHistory({
  disabled,
  failed,
  loading,
  onResume,
  onRetry,
  resumingThreadId,
  threads,
}: {
  disabled: boolean;
  failed: boolean;
  loading: boolean;
  onResume: (thread: AgentTerminalCodexThread) => void;
  onRetry: () => void;
  resumingThreadId: string | null;
  threads: AgentTerminalCodexThread[];
}) {
  const { i18n, t } = useTranslation('apps');
  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'short',
        timeStyle: 'short',
      }),
    [i18n.language],
  );

  if (loading) {
    return (
      <div className="grid place-items-center gap-2 px-3 py-8 text-app-ink/55">
        <RefreshCw aria-hidden="true" className="size-4 animate-spin" />
        <span className="app-text-caption">
          {t('agentTerminal.codexHistory.loading')}
        </span>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="grid place-items-center gap-3 px-3 py-8 text-center">
        <p className="app-text-caption text-app-ink/55">
          {t('agentTerminal.codexHistory.loadFailed')}
        </p>
        <button
          className="inline-flex items-center gap-1.5 rounded-md border border-app-border px-2.5 py-1.5 app-text-caption text-app-ink/70 transition-colors hover:bg-app-surface-hover"
          onClick={onRetry}
          type="button"
        >
          <RefreshCw aria-hidden="true" className="size-3.5" />
          {t('agentTerminal.actions.retry')}
        </button>
      </div>
    );
  }

  if (threads.length === 0) {
    return (
      <div className="grid place-items-center gap-2 px-3 py-8 text-center text-app-ink/55">
        <History aria-hidden="true" className="size-4" />
        <span className="app-text-caption">
          {t('agentTerminal.codexHistory.empty')}
        </span>
      </div>
    );
  }

  return (
    <div className="grid gap-1 p-2">
      {threads.map((thread) => {
        const title =
          thread.name ||
          thread.preview ||
          t('agentTerminal.codexHistory.untitled', {
            id: thread.id.slice(0, 8),
          });
        const resuming = resumingThreadId === thread.id;
        return (
          <div
            className="grid min-w-0 gap-2 rounded-md border border-transparent px-3 py-2.5 hover:border-app-border"
            key={thread.id}
          >
            <span className="line-clamp-3 app-text-label" title={title}>
              {title}
            </span>
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="min-w-0 truncate app-text-caption text-app-ink/50">
                {thread.root_key} ·{' '}
                {dateFormatter.format(new Date(thread.updated_at))}
              </span>
              <button
                aria-label={t('agentTerminal.actions.resumeThreadLabel', {
                  name: title,
                })}
                className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-1 app-text-caption text-app-accent transition-colors hover:bg-app-accent/10 disabled:cursor-not-allowed disabled:opacity-45"
                disabled={disabled || resumingThreadId !== null}
                onClick={() => onResume(thread)}
                title={
                  disabled
                    ? t('agentTerminal.sessionLimitReached')
                    : t('agentTerminal.actions.resume')
                }
                type="button"
              >
                {resuming ? (
                  <RefreshCw
                    aria-hidden="true"
                    className="size-3.5 animate-spin"
                  />
                ) : (
                  <Play aria-hidden="true" className="size-3.5" />
                )}
                {t('agentTerminal.actions.resume')}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
