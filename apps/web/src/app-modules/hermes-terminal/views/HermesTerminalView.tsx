import {
  Badge,
  Button,
  EmptyState,
  InlineNotice,
  Select,
  useFeedback,
} from '@open-work-hub/ui';
import {
  CircleStop,
  Plus,
  RefreshCw,
  ShieldAlert,
  SquareTerminal,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { FormDialog } from '@/src/components/form/FormDialog';
import {
  WebSocketTerminalSurface,
  type TerminalConnectionState,
} from '@/src/components/terminal/WebSocketTerminalSurface';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createHermesTerminalSession,
  getHermesTerminalConfig,
  hermesTerminalWebSocketUrl,
  listHermesTerminalSessions,
  stopHermesTerminalSession,
  type HermesTerminalConfig,
  type HermesTerminalSession,
} from '../api/hermes-terminal-api';
import { HermesTerminalActivityPanel } from './HermesTerminalActivityPanel';

const ACTIVE_STATUSES = new Set<HermesTerminalSession['status']>([
  'starting',
  'running',
  'awaiting_approval',
  'stopping',
  'archiving',
]);
const ATTACHABLE_STATUSES = new Set<HermesTerminalSession['status']>([
  'running',
  'awaiting_approval',
]);

function isActive(session: Pick<HermesTerminalSession, 'status'>): boolean {
  return ACTIVE_STATUSES.has(session.status);
}

function statusTone(
  status: HermesTerminalSession['status'] | TerminalConnectionState,
): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (status === 'running' || status === 'connected') return 'success';
  if (status === 'starting' || status === 'connecting') return 'accent';
  if (status === 'failed' || status === 'offline') return 'danger';
  if (
    status === 'awaiting_approval' ||
    status === 'stopping' ||
    status === 'archiving' ||
    status === 'terminated'
  ) {
    return 'warning';
  }
  return 'neutral';
}

function utcDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

interface SessionsRequest {
  promise: Promise<void>;
  token: string;
}

export function HermesTerminalView() {
  const { i18n, t } = useTranslation('apps');
  const feedback = useFeedback();
  const { token } = useAuth();

  const [config, setConfig] = useState<HermesTerminalConfig | null>(null);
  const [sessions, setSessions] = useState<HermesTerminalSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createMode, setCreateMode] = useState<'standard' | 'yolo'>('standard');
  const [yoloAcknowledged, setYoloAcknowledged] = useState(false);
  const [stoppingSessionId, setStoppingSessionId] = useState<string | null>(
    null,
  );
  const [connectionState, setConnectionState] =
    useState<TerminalConnectionState>('offline');
  const [terminalVersion, setTerminalVersion] = useState(0);
  const sessionsRequestRef = useRef<SessionsRequest | null>(null);
  const loadAllRequestRef = useRef(0);
  const requestContextRef = useRef({ token });
  requestContextRef.current = { token };

  const applySessions = useCallback((items: HermesTerminalSession[]) => {
    setSessions(items);
    setSelectedSessionId((current) => {
      if (current && items.some((session) => session.id === current))
        return current;
      return items.find(isActive)?.id ?? items[0]?.id ?? null;
    });
  }, []);

  const loadSessions = useCallback(() => {
    if (!token) return Promise.resolve();
    const current = sessionsRequestRef.current;
    if (current?.token === token) {
      return current.promise;
    }
    const request: SessionsRequest = {
      promise: Promise.resolve(),
      token,
    };
    request.promise = listHermesTerminalSessions(token)
      .then((response) => {
        if (
          sessionsRequestRef.current === request &&
          requestContextRef.current.token === token
        ) {
          applySessions(response.items ?? []);
        }
      })
      .finally(() => {
        if (sessionsRequestRef.current === request) {
          sessionsRequestRef.current = null;
        }
      });
    sessionsRequestRef.current = request;
    return request.promise;
  }, [applySessions, token]);

  const loadAll = useCallback(async () => {
    const requestId = loadAllRequestRef.current + 1;
    loadAllRequestRef.current = requestId;
    if (!token) {
      setLoading(false);
      setLoadFailed(true);
      return;
    }
    setLoading(true);
    try {
      const [nextConfig, response] = await Promise.all([
        getHermesTerminalConfig(token),
        listHermesTerminalSessions(token),
      ]);
      if (
        loadAllRequestRef.current !== requestId ||
        requestContextRef.current.token !== token
      ) {
        return;
      }
      setConfig(nextConfig);
      applySessions(response.items ?? []);
      setLoadFailed(false);
    } catch {
      if (
        loadAllRequestRef.current !== requestId ||
        requestContextRef.current.token !== token
      ) {
        return;
      }
      setLoadFailed(true);
      feedback.error(t('hermesTerminal.feedback.loadFailed'));
    } finally {
      if (
        loadAllRequestRef.current === requestId &&
        requestContextRef.current.token === token
      ) {
        setLoading(false);
      }
    }
  }, [applySessions, feedback, t, token]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const hasActiveSession = sessions.some(isActive);
  useEffect(() => {
    if (!hasActiveSession) return;
    let cancelled = false;
    let timer: number | null = null;
    const poll = async () => {
      if (cancelled) return;
      if (document.visibilityState === 'visible') {
        await loadSessions().catch(() => undefined);
      }
      if (!cancelled) {
        timer = window.setTimeout(
          () => void poll(),
          document.visibilityState === 'visible' ? 3000 : 10_000,
        );
      }
    };
    timer = window.setTimeout(() => void poll(), 3000);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [hasActiveSession, loadSessions]);

  const selectedSession =
    sessions.find((session) => session.id === selectedSessionId) ?? null;
  const selectedSessionStatus = selectedSession?.status;
  useEffect(() => {
    setConnectionState(
      selectedSessionStatus && ATTACHABLE_STATUSES.has(selectedSessionStatus)
        ? 'connecting'
        : 'ended',
    );
  }, [selectedSessionId, selectedSessionStatus]);

  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'short',
        timeStyle: 'short',
      }),
    [i18n.language],
  );
  const sessionOptions = useMemo(
    () =>
      sessions.map((session) => ({
        value: session.id,
        label: `${session.title} · ${t(`hermesTerminal.status.${session.status}`)}`,
      })),
    [sessions, t],
  );
  const activeCount = sessions.filter(isActive).length;
  const sessionLimitReached =
    activeCount >= (config?.max_sessions_per_user ?? 1);

  const openCreateDialog = useCallback(() => {
    setCreateMode('standard');
    setYoloAcknowledged(false);
    setCreateDialogOpen(true);
  }, []);
  const closeCreateDialog = useCallback(() => {
    if (creating) return;
    setCreateDialogOpen(false);
    setCreateMode('standard');
    setYoloAcknowledged(false);
  }, [creating]);

  const createSession = useCallback(async () => {
    if (
      !token ||
      creating ||
      sessionLimitReached ||
      (createMode === 'yolo' && !yoloAcknowledged)
    ) {
      return;
    }
    setCreating(true);
    const knownSessionIds = new Set(sessions.map((session) => session.id));
    try {
      const session = await createHermesTerminalSession(token, {
        mode: createMode,
        risk_acknowledged: createMode === 'yolo' && yoloAcknowledged,
        cols: 120,
        rows: 36,
      });
      if (requestContextRef.current.token !== token) {
        return;
      }
      setSessions((current) => [session, ...current]);
      setSelectedSessionId(session.id);
      setCreateDialogOpen(false);
      setCreateMode('standard');
      setYoloAcknowledged(false);
      feedback.success(t('hermesTerminal.feedback.created'));
    } catch {
      if (requestContextRef.current.token !== token) {
        return;
      }
      try {
        const response = await listHermesTerminalSessions(token);
        if (requestContextRef.current.token !== token) {
          return;
        }
        const items = response.items ?? [];
        applySessions(items);
        const adopted = items.find(
          (session) => !knownSessionIds.has(session.id) && isActive(session),
        );
        if (adopted) {
          setSelectedSessionId(adopted.id);
          setCreateDialogOpen(false);
          setCreateMode('standard');
          setYoloAcknowledged(false);
          feedback.success(t('hermesTerminal.feedback.created'));
          return;
        }
      } catch {
        // Preserve the original create failure when reconciliation also fails.
      }
      feedback.error(t('hermesTerminal.feedback.createFailed'));
    } finally {
      setCreating(false);
    }
  }, [
    createMode,
    creating,
    feedback,
    applySessions,
    sessionLimitReached,
    sessions,
    t,
    token,
    yoloAcknowledged,
  ]);

  const stopSession = useCallback(
    async (session: HermesTerminalSession) => {
      if (!token || !isActive(session)) return;
      setStoppingSessionId(session.id);
      try {
        const stopped = await stopHermesTerminalSession(token, session.id);
        if (requestContextRef.current.token !== token) {
          return;
        }
        setSessions((current) =>
          current.map((item) => (item.id === stopped.id ? stopped : item)),
        );
        feedback.success(t('hermesTerminal.feedback.stopped'));
      } catch {
        if (requestContextRef.current.token === token) {
          feedback.error(t('hermesTerminal.feedback.stopFailed'));
        }
      } finally {
        setStoppingSessionId(null);
      }
    },
    [feedback, t, token],
  );

  const handleTerminalExit = useCallback(() => {
    void loadSessions().catch(() => undefined);
  }, [loadSessions]);
  const handleTerminalError = useCallback(() => {
    feedback.error(t('hermesTerminal.feedback.connectionFailed'));
  }, [feedback, t]);

  if (loading) {
    return (
      <div className="grid h-full place-items-center bg-app-bg text-app-ink/60">
        <RefreshCw aria-hidden="true" className="size-5 animate-spin" />
        <span className="sr-only">{t('hermesTerminal.loading')}</span>
      </div>
    );
  }
  if (loadFailed || !config || !token) {
    return (
      <div className="grid h-full place-items-center bg-app-bg p-6">
        <EmptyState
          action={{
            label: t('hermesTerminal.actions.retry'),
            onClick: () => void loadAll(),
          }}
          title={t('hermesTerminal.loadFailedTitle')}
          description={t('hermesTerminal.loadFailedDescription')}
        />
      </div>
    );
  }

  const canCreate = config.enabled && !sessionLimitReached && !creating;
  const selectedAttachable = Boolean(
    selectedSession && ATTACHABLE_STATUSES.has(selectedSession.status),
  );

  return (
    <>
      <div className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-app-border px-4 py-3">
          <div className="min-w-0">
            <p className="app-text-caption text-app-ink/55">
              {t('hermesTerminal.eyebrow')}
            </p>
            <div className="flex items-center gap-2">
              <SquareTerminal
                aria-hidden="true"
                className="size-5 text-app-accent"
              />
              <h1 className="truncate app-text-title-md">
                {t('hermesTerminal.title')}
              </h1>
              <Badge tone="neutral">{config.model}</Badge>
            </div>
          </div>
          <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
            {sessionOptions.length > 0 ? (
              <Select
                ariaLabel={t('hermesTerminal.sessionsLabel')}
                className="max-w-[min(480px,55vw)]"
                onValueChange={setSelectedSessionId}
                options={sessionOptions}
                value={selectedSessionId ?? ''}
              />
            ) : null}
            <Badge tone={sessionLimitReached ? 'warning' : 'neutral'}>
              {t('hermesTerminal.sessionCapacity', {
                active: activeCount,
                limit: config.max_sessions_per_user,
              })}
            </Badge>
            <Button
              disabled={!canCreate}
              onClick={openCreateDialog}
              title={
                sessionLimitReached
                  ? t('hermesTerminal.sessionLimitReached')
                  : undefined
              }
              variant="primary"
            >
              <Plus aria-hidden="true" className="size-4" />
              {t('hermesTerminal.actions.newSession')}
            </Button>
            <Button onClick={() => void loadAll()}>
              <RefreshCw aria-hidden="true" className="size-4" />
              {t('hermesTerminal.actions.refresh')}
            </Button>
          </div>
        </header>

        {!config.enabled ? (
          <div className="grid flex-1 place-items-center p-6">
            <EmptyState
              title={t('hermesTerminal.unavailableTitle')}
              description={t('hermesTerminal.disabledDescription')}
            />
          </div>
        ) : selectedSession ? (
          <div className="flex min-h-0 flex-1 flex-col xl:flex-row">
            <main className="flex min-h-0 min-w-0 flex-1 flex-col">
              <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-app-border bg-app-surface px-3 py-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="truncate app-text-label">
                      {selectedSession.title}
                    </span>
                    <Badge tone={statusTone(selectedSession.status)}>
                      {t(`hermesTerminal.status.${selectedSession.status}`)}
                    </Badge>
                    <Badge
                      tone={
                        selectedSession.mode === 'yolo' ? 'warning' : 'neutral'
                      }
                    >
                      {t(`hermesTerminal.mode.${selectedSession.mode}`)}
                    </Badge>
                    {selectedAttachable ? (
                      <Badge tone={statusTone(connectionState)}>
                        {t(`hermesTerminal.connection.${connectionState}`)}
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-0.5 app-text-caption text-app-ink/50">
                    {dateFormatter.format(utcDate(selectedSession.created_at))}{' '}
                    · {t('hermesTerminal.privateWorkspace')}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {selectedAttachable && connectionState === 'offline' ? (
                    <Button
                      onClick={() => {
                        setConnectionState('connecting');
                        setTerminalVersion((current) => current + 1);
                      }}
                      variant="subtle"
                    >
                      <RefreshCw aria-hidden="true" className="size-4" />
                      {t('hermesTerminal.actions.reconnect')}
                    </Button>
                  ) : null}
                  {isActive(selectedSession) ? (
                    <Button
                      disabled={stoppingSessionId !== null}
                      onClick={() => void stopSession(selectedSession)}
                      variant="subtle"
                    >
                      {stoppingSessionId === selectedSession.id ? (
                        <RefreshCw
                          aria-hidden="true"
                          className="size-4 animate-spin"
                        />
                      ) : (
                        <CircleStop aria-hidden="true" className="size-4" />
                      )}
                      {t('hermesTerminal.actions.stop')}
                    </Button>
                  ) : null}
                </div>
              </div>
              {selectedSession.workspace_retained ? (
                <InlineNotice role="alert" tone="warning">
                  {t('hermesTerminal.archive.workspaceRetained')}
                </InlineNotice>
              ) : selectedSession.artifact_omitted_count > 0 ? (
                <InlineNotice role="status" tone="warning">
                  {t('hermesTerminal.archive.partial', {
                    count: selectedSession.artifact_omitted_count,
                  })}
                </InlineNotice>
              ) : null}
              <div className="min-h-0 flex-1 bg-[var(--ui-color-surface-inverse)]">
                {selectedAttachable ? (
                  <WebSocketTerminalSurface
                    ariaLabel={t('hermesTerminal.terminalLabel')}
                    key={`${selectedSession.id}:${terminalVersion}`}
                    onConnectionStateChange={setConnectionState}
                    onError={handleTerminalError}
                    onExit={handleTerminalExit}
                    token={token}
                    webSocketUrl={hermesTerminalWebSocketUrl(
                      selectedSession.id,
                    )}
                  />
                ) : (
                  <div className="grid h-full place-items-center bg-app-bg p-6">
                    <EmptyState
                      title={
                        isActive(selectedSession)
                          ? t('hermesTerminal.preparingTitle')
                          : t('hermesTerminal.sessionEndedTitle')
                      }
                      description={
                        isActive(selectedSession)
                          ? t('hermesTerminal.preparingDescription')
                          : selectedSession.failure_code
                            ? t('hermesTerminal.failureDescription', {
                                code: selectedSession.failure_code,
                              })
                            : t('hermesTerminal.sessionEndedDescription')
                      }
                    />
                  </div>
                )}
              </div>
            </main>
            <aside className="h-[min(42%,360px)] min-h-[220px] shrink-0 border-t border-app-border xl:h-auto xl:min-h-0 xl:w-[390px] xl:border-l xl:border-t-0">
              <HermesTerminalActivityPanel
                session={selectedSession}
                token={token}
              />
            </aside>
          </div>
        ) : (
          <div className="grid flex-1 place-items-center p-6">
            <EmptyState
              action={{
                label: t('hermesTerminal.actions.newSession'),
                onClick: openCreateDialog,
              }}
              title={t('hermesTerminal.noSessionTitle')}
              description={t('hermesTerminal.noSessionDescription')}
            />
          </div>
        )}

        <footer className="flex shrink-0 items-center gap-2 border-t border-app-border bg-app-surface px-4 py-2 app-text-caption text-app-ink/55">
          <ShieldAlert aria-hidden="true" className="size-4 shrink-0" />
          <span>{t('hermesTerminal.securityNotice')}</span>
        </footer>
      </div>

      <FormDialog
        cancelLabel={t('hermesTerminal.actions.cancel')}
        closeLabel={t('hermesTerminal.actions.cancel')}
        description={t('hermesTerminal.create.description')}
        dismissOnInteractOutside={false}
        onCancel={closeCreateDialog}
        onPrimary={() => void createSession()}
        open={createDialogOpen}
        primaryDisabled={createMode === 'yolo' && !yoloAcknowledged}
        primaryLabel={t('hermesTerminal.create.start')}
        primaryPendingLabel={t('hermesTerminal.create.starting')}
        submitting={creating}
        title={t('hermesTerminal.create.title')}
      >
        <div className="space-y-3 text-app-ink">
          <label className="flex cursor-pointer items-start gap-3 rounded-md border border-app-border p-3 hover:bg-app-surface-hover">
            <input
              checked={createMode === 'standard'}
              className="mt-0.5 size-4 accent-[var(--ui-color-accent)]"
              name="hermes-terminal-mode"
              onChange={() => {
                setCreateMode('standard');
                setYoloAcknowledged(false);
              }}
              type="radio"
            />
            <span>
              <span className="block app-text-label">
                {t('hermesTerminal.create.standardTitle')}
              </span>
              <span className="mt-0.5 block app-text-caption text-app-ink/55">
                {t('hermesTerminal.create.standardDescription')}
              </span>
            </span>
          </label>
          <label className="flex cursor-pointer items-start gap-3 rounded-md border border-[var(--ui-color-warning)]/40 p-3 hover:bg-[var(--ui-color-warning)]/5">
            <input
              checked={createMode === 'yolo'}
              className="mt-0.5 size-4 accent-[var(--ui-color-warning)]"
              name="hermes-terminal-mode"
              onChange={() => setCreateMode('yolo')}
              type="radio"
            />
            <span>
              <span className="block app-text-label">
                {t('hermesTerminal.create.yoloTitle')}
              </span>
              <span className="mt-0.5 block app-text-caption text-app-ink/55">
                {t('hermesTerminal.create.yoloDescription')}
              </span>
            </span>
          </label>
          {createMode === 'yolo' ? (
            <label className="flex cursor-pointer items-start gap-3 bg-[var(--ui-color-warning)]/5 px-3 py-2">
              <input
                checked={yoloAcknowledged}
                className="mt-0.5 size-4 accent-[var(--ui-color-warning)]"
                onChange={(event) => setYoloAcknowledged(event.target.checked)}
                type="checkbox"
              />
              <span className="app-text-caption text-app-ink/75">
                {t('hermesTerminal.create.yoloAcknowledgement')}
              </span>
            </label>
          ) : null}
        </div>
      </FormDialog>
    </>
  );
}
