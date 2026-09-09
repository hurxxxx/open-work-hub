import {
  Activity,
  Pause,
  Play,
  RefreshCcw,
  Square,
  TimerReset,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import type { LlmHealthResponse } from '../../api/chatbot-api';
import {
  listHermesJobs,
  listHermesRuns,
  runHermesJobAction,
  stopHermesRun,
  type HermesJob,
  type HermesRun,
} from '../../api/hermes-agent-api';

const ACTIVE_RUN_STATUSES = new Set([
  'pending',
  'dispatching',
  'queued',
  'running',
  'awaiting_approval',
  'stopping',
]);

interface AgentControlMenuProps {
  health: LlmHealthResponse | null;
  healthError: string | null;
}

export function AgentControlMenu({
  health,
  healthError,
}: AgentControlMenuProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<HermesRun[]>([]);
  const [jobs, setJobs] = useState<HermesJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionKey, setActionKey] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [runPage, jobPage] = await Promise.all([
        listHermesRuns(token, { limit: 10 }),
        listHermesJobs(token),
      ]);
      setRuns(runPage.data);
      setJobs(jobPage.data);
      setError(null);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.agentControl.loadFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [t, token]);

  useEffect(() => {
    if (!open) return;
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 3_000);
    return () => window.clearInterval(interval);
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', closeOnEscape);
    };
  }, [open]);

  const stopRun = async (run: HermesRun) => {
    if (!token) return;
    setActionKey(`run:${run.id}`);
    try {
      await stopHermesRun(token, run.id);
      await refresh();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.agentControl.actionFailed'),
      );
    } finally {
      setActionKey(null);
    }
  };

  const updateJob = async (
    job: HermesJob,
    action: 'pause' | 'resume' | 'run',
  ) => {
    if (!token) return;
    setActionKey(`job:${job.id}:${action}`);
    try {
      await runHermesJobAction(token, job.id, action);
      await refresh();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t('ai.agentControl.actionFailed'),
      );
    } finally {
      setActionKey(null);
    }
  };

  const ready = Boolean(health?.ready) && !healthError;
  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((current) => !current)}
        className="app-text-control-sm flex h-8 items-center gap-2 rounded-full border border-app-border bg-app-surface px-3 text-app-ink transition-colors hover:border-app-accent"
      >
        <span
          className={`h-2 w-2 rounded-full ${ready ? 'bg-app-success' : 'bg-app-warning'}`}
        />
        <span className="hidden sm:inline">Hermes · Qwen 3.8 Flash</span>
        <Activity size={14} aria-hidden="true" />
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label={t('ai.agentControl.title')}
          className="absolute right-0 top-10 z-50 w-[min(92vw,28rem)] overflow-hidden rounded-xl border border-app-border bg-app-surface shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-app-border px-4 py-3">
            <div>
              <p className="app-text-control text-app-ink">
                {t('ai.agentControl.title')}
              </p>
              <p className="app-text-micro text-app-ink/55">
                {t('ai.agentControl.runtime')}
              </p>
            </div>
            <button
              type="button"
              aria-label={t('ai.agentControl.refresh')}
              disabled={loading}
              onClick={() => void refresh()}
              className="rounded-md p-2 text-app-ink/60 hover:bg-app-surface-hover hover:text-app-ink disabled:opacity-50"
            >
              <RefreshCcw size={15} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>

          <div className="custom-scrollbar max-h-[70vh] space-y-4 overflow-y-auto p-4">
            {error || healthError ? (
              <p className="app-text-caption rounded-md bg-app-warning/10 px-3 py-2 text-app-warning-text">
                {error ?? healthError}
              </p>
            ) : null}

            <ControlSection title={t('ai.agentControl.recentRuns')}>
              {runs.length === 0 ? (
                <EmptyRow text={t('ai.agentControl.noRuns')} />
              ) : (
                runs.map((run) => {
                  const active = ACTIVE_RUN_STATUSES.has(run.status);
                  return (
                    <div
                      key={run.id}
                      className="rounded-lg border border-app-border bg-app-bg px-3 py-2"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="app-text-control-sm truncate text-app-ink">
                            {run.current_activity || run.stage || run.status}
                          </p>
                          <p className="app-text-micro text-app-ink/50">
                            {run.status} · {run.progress_percent}%
                          </p>
                        </div>
                        {active ? (
                          <button
                            type="button"
                            aria-label={t('ai.agentControl.stopRun')}
                            disabled={actionKey === `run:${run.id}`}
                            onClick={() => void stopRun(run)}
                            className="rounded-md border border-app-border p-1.5 text-app-ink/60 hover:border-app-danger hover:text-app-danger-text disabled:opacity-50"
                          >
                            <Square size={12} />
                          </button>
                        ) : null}
                      </div>
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-app-border">
                        <div
                          className="h-full rounded-full bg-app-accent transition-[width]"
                          style={{
                            width: `${Math.max(0, Math.min(100, run.progress_percent))}%`,
                          }}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </ControlSection>

            <ControlSection title={t('ai.agentControl.scheduledJobs')}>
              {jobs.length === 0 ? (
                <EmptyRow text={t('ai.agentControl.noJobs')} />
              ) : (
                jobs.map((job) => (
                  <div
                    key={job.id}
                    className="flex items-center justify-between gap-3 rounded-lg border border-app-border bg-app-bg px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="app-text-control-sm truncate text-app-ink">
                        {job.name}
                      </p>
                      <p className="app-text-micro truncate text-app-ink/50">
                        {job.schedule || job.status}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <JobButton
                        label={t('ai.agentControl.runNow')}
                        disabled={actionKey !== null}
                        onClick={() => void updateJob(job, 'run')}
                      >
                        <TimerReset size={12} />
                      </JobButton>
                      {job.status === 'paused' ? (
                        <JobButton
                          label={t('ai.agentControl.resumeJob')}
                          disabled={actionKey !== null}
                          onClick={() => void updateJob(job, 'resume')}
                        >
                          <Play size={12} />
                        </JobButton>
                      ) : (
                        <JobButton
                          label={t('ai.agentControl.pauseJob')}
                          disabled={actionKey !== null}
                          onClick={() => void updateJob(job, 'pause')}
                        >
                          <Pause size={12} />
                        </JobButton>
                      )}
                    </div>
                  </div>
                ))
              )}
            </ControlSection>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ControlSection({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="space-y-2">
      <h2 className="app-text-overline text-app-ink/50">{title}</h2>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function EmptyRow({ text }: { text: string }) {
  return (
    <p className="app-text-caption rounded-lg border border-dashed border-app-border px-3 py-3 text-app-ink/45">
      {text}
    </p>
  );
}

function JobButton({
  children,
  disabled,
  label,
  onClick,
}: {
  children: React.ReactNode;
  disabled: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="rounded-md border border-app-border p-1.5 text-app-ink/60 hover:border-app-accent hover:text-app-accent disabled:opacity-40"
    >
      {children}
    </button>
  );
}
