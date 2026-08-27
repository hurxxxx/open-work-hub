import {
  Badge,
  Button,
  DetailDrawer,
  EmptyState,
  Select,
  useConfirm,
  useFeedback,
} from '@open-work-hub/ui';
import {
  CircleStop,
  GitBranch,
  Plus,
  RefreshCw,
  ShieldAlert,
  SquareTerminal,
  Trash2,
} from 'lucide-react';
import { Group, Panel, Separator } from 'react-resizable-panels';
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from 'react';
import { useTranslation } from 'react-i18next';

import { hasAnySystemRole } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  createAgentTerminalSession,
  deleteAgentTerminalSession,
  getAgentTerminalConfig,
  listAgentTerminalSessions,
  stopAgentTerminalSession,
  type AgentTerminalConfig,
  type AgentTerminalSession,
} from '../api/agent-terminal-api';
import { AgentTerminalGitPanel } from './AgentTerminalGitPanel';
import { AgentTerminalSurface } from './AgentTerminalSurface';

type TerminalConnectionState = 'connecting' | 'connected' | 'ended' | 'offline';

const ACTIVE_SESSION_STATUSES = new Set(['starting', 'running']);

function badgeTone(
  status: string,
): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (status === 'running' || status === 'connected') return 'success';
  if (status === 'starting' || status === 'connecting') return 'accent';
  if (status === 'failed' || status === 'offline') return 'danger';
  if (status === 'terminated') return 'warning';
  return 'neutral';
}

function utcDate(value: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

function getMediaQuerySnapshot(query: string): boolean {
  return typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function'
    ? window.matchMedia(query).matches
    : false;
}

function subscribeMediaQuery(
  query: string,
  onStoreChange: () => void,
): () => void {
  if (
    typeof window === 'undefined' ||
    typeof window.matchMedia !== 'function'
  ) {
    return () => undefined;
  }

  const mediaQuery = window.matchMedia(query);
  mediaQuery.addEventListener('change', onStoreChange);
  return () => mediaQuery.removeEventListener('change', onStoreChange);
}

function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    useCallback(
      (onStoreChange) => subscribeMediaQuery(query, onStoreChange),
      [query],
    ),
    useCallback(() => getMediaQuerySnapshot(query), [query]),
    () => false,
  );
}

export function AgentTerminalView() {
  const { i18n, t } = useTranslation('apps');
  const feedback = useFeedback();
  const { confirm, confirmDialog } = useConfirm();
  const { token, user } = useAuth();
  const isPlatformAdmin = hasAnySystemRole(user, ['platform_admin']);
  const [config, setConfig] = useState<AgentTerminalConfig | null>(null);
  const [sessions, setSessions] = useState<AgentTerminalSession[]>([]);
  const [selectedRootKey, setSelectedRootKey] = useState('');
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(
    null,
  );
  const [connectionState, setConnectionState] =
    useState<TerminalConnectionState>('offline');
  const [terminalSurfaceVersion, setTerminalSurfaceVersion] = useState(0);
  const [gitPanelOpen, setGitPanelOpen] = useState(false);
  const gitPanelDocked = useMediaQuery('(min-width: 1280px)');

  const loadSessions = useCallback(async () => {
    if (!token) return;
    const response = await listAgentTerminalSessions(token);
    const items = response.items ?? [];
    setSessions(items);
    setSelectedSessionId((current) => {
      if (current && items.some((session) => session.id === current)) {
        return current;
      }
      return (
        items.find((session) => ACTIVE_SESSION_STATUSES.has(session.status))
          ?.id ??
        items[0]?.id ??
        null
      );
    });
  }, [token]);

  const loadAll = useCallback(async () => {
    if (!token || !isPlatformAdmin) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [nextConfig, response] = await Promise.all([
        getAgentTerminalConfig(token),
        listAgentTerminalSessions(token),
      ]);
      const roots = nextConfig.roots ?? [];
      const items = response.items ?? [];
      setConfig(nextConfig);
      setSessions(items);
      setSelectedRootKey((current) =>
        roots.some((root) => root.key === current)
          ? current
          : (roots[0]?.key ?? ''),
      );
      setSelectedSessionId((current) => {
        if (current && items.some((session) => session.id === current)) {
          return current;
        }
        return (
          items.find((session) => ACTIVE_SESSION_STATUSES.has(session.status))
            ?.id ??
          items[0]?.id ??
          null
        );
      });
      setLoadFailed(false);
    } catch {
      setLoadFailed(true);
      feedback.error(t('agentTerminal.feedback.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [feedback, isPlatformAdmin, t, token]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const hasActiveSession = sessions.some((session) =>
    ACTIVE_SESSION_STATUSES.has(session.status),
  );
  useEffect(() => {
    if (!hasActiveSession) return;
    const timer = window.setInterval(() => {
      void loadSessions().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [hasActiveSession, loadSessions]);

  const selectedSession =
    sessions.find((session) => session.id === selectedSessionId) ?? null;
  useEffect(() => {
    setConnectionState(
      selectedSession && ACTIVE_SESSION_STATUSES.has(selectedSession.status)
        ? 'connecting'
        : 'ended',
    );
  }, [selectedSession?.id, selectedSession?.status]);
  useEffect(() => {
    setGitPanelOpen(false);
  }, [gitPanelDocked, selectedSessionId]);
  const rootOptions = useMemo(
    () =>
      (config?.roots ?? []).map((root) => ({
        value: root.key,
        label: `${root.label} · ${root.path}`,
      })),
    [config?.roots],
  );
  const dateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language, {
        dateStyle: 'short',
        timeStyle: 'short',
      }),
    [i18n.language],
  );

  const createSession = useCallback(async () => {
    if (!token || !selectedRootKey) return;
    setCreating(true);
    try {
      const session = await createAgentTerminalSession(token, {
        root_key: selectedRootKey,
        cols: 120,
        rows: 36,
      });
      setSessions((current) => [session, ...current]);
      setSelectedSessionId(session.id);
      feedback.success(t('agentTerminal.feedback.created'));
    } catch {
      feedback.error(t('agentTerminal.feedback.createFailed'));
    } finally {
      setCreating(false);
    }
  }, [feedback, selectedRootKey, t, token]);

  const stopSession = useCallback(async () => {
    if (!token || !selectedSession) return;
    setStopping(true);
    try {
      const stopped = await stopAgentTerminalSession(token, selectedSession.id);
      setSessions((current) =>
        current.map((session) =>
          session.id === stopped.id ? stopped : session,
        ),
      );
      feedback.success(t('agentTerminal.feedback.stopped'));
    } catch {
      feedback.error(t('agentTerminal.feedback.stopFailed'));
    } finally {
      setStopping(false);
    }
  }, [feedback, selectedSession, t, token]);

  const deleteSession = useCallback(
    async (session: AgentTerminalSession) => {
      if (!token || ACTIVE_SESSION_STATUSES.has(session.status)) return;
      const confirmed = await confirm({
        title: t('agentTerminal.deleteConfirmTitle'),
        description: t('agentTerminal.deleteConfirmDescription', {
          root: session.root_key,
        }),
        confirmLabel: t('agentTerminal.actions.delete'),
        cancelLabel: t('agentTerminal.actions.cancel'),
        variant: 'danger',
      });
      if (!confirmed) return;

      setDeletingSessionId(session.id);
      try {
        await deleteAgentTerminalSession(token, session.id);
        const remaining = sessions.filter((item) => item.id !== session.id);
        setSessions(remaining);
        if (selectedSessionId === session.id) {
          setSelectedSessionId(
            remaining.find((item) => ACTIVE_SESSION_STATUSES.has(item.status))
              ?.id ??
              remaining[0]?.id ??
              null,
          );
        }
        feedback.success(t('agentTerminal.feedback.deleted'));
      } catch {
        feedback.error(t('agentTerminal.feedback.deleteFailed'));
      } finally {
        setDeletingSessionId(null);
      }
    },
    [confirm, feedback, selectedSessionId, sessions, t, token],
  );

  const handleTerminalExit = useCallback(() => {
    void loadSessions().catch(() => undefined);
  }, [loadSessions]);
  const handleTerminalError = useCallback(() => {
    feedback.error(t('agentTerminal.feedback.connectionFailed'));
  }, [feedback, t]);
  const reconnectTerminal = useCallback(() => {
    setConnectionState('connecting');
    setTerminalSurfaceVersion((current) => current + 1);
  }, []);

  if (!isPlatformAdmin) {
    return (
      <div className="grid h-full place-items-center bg-app-bg p-6">
        <EmptyState
          title={t('agentTerminal.accessDeniedTitle')}
          description={t('agentTerminal.accessDeniedDescription')}
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="grid h-full place-items-center bg-app-bg text-app-ink/60">
        <RefreshCw aria-hidden="true" className="size-5 animate-spin" />
        <span className="sr-only">{t('agentTerminal.loading')}</span>
      </div>
    );
  }

  if (loadFailed || !config) {
    return (
      <div className="grid h-full place-items-center bg-app-bg p-6">
        <EmptyState
          action={{
            label: t('agentTerminal.actions.retry'),
            onClick: () => void loadAll(),
          }}
          title={t('agentTerminal.loadFailedTitle')}
          description={t('agentTerminal.loadFailedDescription')}
        />
      </div>
    );
  }

  const canCreate =
    config.enabled &&
    config.codex_available &&
    config.tmux_available &&
    rootOptions.length > 0 &&
    Boolean(selectedRootKey) &&
    !creating;
  const selectedIsActive = Boolean(
    selectedSession && ACTIVE_SESSION_STATUSES.has(selectedSession.status),
  );
  const terminalSurface = selectedSession ? (
    <div className="h-full min-h-0 bg-[var(--ui-color-surface-inverse)]">
      {selectedSession.status === 'failed' ? (
        <div className="grid h-full place-items-center bg-app-bg p-6">
          <EmptyState
            title={t('agentTerminal.failedSessionTitle')}
            description={t('agentTerminal.failedSessionDescription')}
          />
        </div>
      ) : token ? (
        <AgentTerminalSurface
          ariaLabel={t('agentTerminal.terminalLabel')}
          key={`${selectedSession.id}:${terminalSurfaceVersion}`}
          onConnectionStateChange={setConnectionState}
          onError={handleTerminalError}
          onExit={handleTerminalExit}
          sessionId={selectedSession.id}
          token={token}
        />
      ) : null}
    </div>
  ) : null;

  return (
    <>
      <div className="flex h-full min-h-0 flex-col bg-app-bg text-app-ink">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-app-border px-4 py-3">
          <div className="min-w-0">
            <p className="app-text-caption text-app-ink/55">
              {t('agentTerminal.eyebrow')}
            </p>
            <div className="flex items-center gap-2">
              <SquareTerminal
                aria-hidden="true"
                className="size-5 text-app-accent"
              />
              <h1 className="app-text-title-md truncate">
                {t('agentTerminal.title')}
              </h1>
            </div>
          </div>
          <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
            <Select
              ariaLabel={t('agentTerminal.rootPlaceholder')}
              className="max-w-[min(480px,48vw)]"
              disabled={rootOptions.length === 0 || creating}
              onValueChange={setSelectedRootKey}
              options={rootOptions}
              placeholder={t('agentTerminal.rootPlaceholder')}
              value={selectedRootKey}
            />
            <Button
              disabled={!canCreate}
              onClick={() => void createSession()}
              variant="primary"
            >
              {creating ? (
                <RefreshCw aria-hidden="true" className="size-4 animate-spin" />
              ) : (
                <Plus aria-hidden="true" className="size-4" />
              )}
              {t('agentTerminal.actions.newSession')}
            </Button>
            <Button onClick={() => void loadAll()}>
              <RefreshCw aria-hidden="true" className="size-4" />
              {t('agentTerminal.actions.refresh')}
            </Button>
          </div>
        </header>

        {!config.enabled ||
        !config.codex_available ||
        !config.tmux_available ||
        rootOptions.length === 0 ? (
          <div className="grid flex-1 place-items-center p-6">
            <EmptyState
              title={t('agentTerminal.unavailableTitle')}
              description={
                !config.enabled
                  ? t('agentTerminal.disabledDescription')
                  : !config.codex_available
                    ? t('agentTerminal.codexMissingDescription')
                    : !config.tmux_available
                      ? t('agentTerminal.tmuxMissingDescription')
                      : t('agentTerminal.rootsMissingDescription')
              }
            />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col md:flex-row">
            <aside className="flex max-h-[34%] w-full shrink-0 flex-col border-b border-app-border bg-app-surface md:max-h-none md:w-[300px] md:border-b-0 md:border-r">
              <div className="border-b border-app-border px-3 py-3">
                <h2 className="app-text-label">
                  {t('agentTerminal.sessionsTitle')}
                </h2>
                <p className="mt-1 app-text-caption text-app-ink/55">
                  {t('agentTerminal.sessionsDescription')}
                </p>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-2">
                {sessions.length === 0 ? (
                  <div className="px-2 py-8 text-center app-text-caption text-app-ink/55">
                    {t('agentTerminal.sessionsEmpty')}
                  </div>
                ) : (
                  <div className="grid gap-1">
                    {sessions.map((session) => {
                      const sessionIsActive = ACTIVE_SESSION_STATUSES.has(
                        session.status,
                      );
                      const sessionIsDeleting =
                        deletingSessionId === session.id;
                      return (
                        <div
                          className={`flex w-full overflow-hidden rounded-md border transition-colors ${
                            session.id === selectedSessionId
                              ? 'border-app-accent bg-app-accent/10'
                              : 'border-transparent'
                          }`}
                          key={session.id}
                        >
                          <button
                            className="grid min-w-0 flex-1 gap-1 px-3 py-2 text-left hover:bg-app-surface-hover"
                            onClick={() => setSelectedSessionId(session.id)}
                            type="button"
                          >
                            <span className="flex items-center justify-between gap-2">
                              <span className="truncate app-text-label">
                                {session.root_key}
                              </span>
                              <Badge tone={badgeTone(session.status)}>
                                {t(`agentTerminal.status.${session.status}`)}
                              </Badge>
                            </span>
                            <span className="truncate app-text-caption text-app-ink/50">
                              {dateFormatter.format(
                                utcDate(session.created_at),
                              )}
                            </span>
                          </button>
                          {!sessionIsActive ? (
                            <button
                              aria-label={t(
                                'agentTerminal.actions.deleteSessionLabel',
                                { root: session.root_key },
                              )}
                              className="inline-flex w-10 shrink-0 items-center justify-center border-l border-app-border text-[var(--ui-color-danger)] transition-colors hover:bg-[var(--ui-color-danger)]/10 disabled:opacity-50"
                              disabled={sessionIsDeleting}
                              onClick={() => void deleteSession(session)}
                              title={t('agentTerminal.actions.delete')}
                              type="button"
                            >
                              {sessionIsDeleting ? (
                                <RefreshCw
                                  aria-hidden="true"
                                  className="size-4 animate-spin"
                                />
                              ) : (
                                <Trash2 aria-hidden="true" className="size-4" />
                              )}
                            </button>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </aside>

            <main className="flex min-w-0 flex-1 flex-col">
              {selectedSession ? (
                <>
                  <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-app-border bg-app-surface px-3 py-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="truncate app-text-label">
                          {selectedSession.root_path}
                        </span>
                        <Badge tone={badgeTone(connectionState)}>
                          {t(`agentTerminal.connection.${connectionState}`)}
                        </Badge>
                      </div>
                      <p className="mt-0.5 app-text-caption text-app-ink/50">
                        {t('agentTerminal.noTranscriptStorage')}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {!gitPanelDocked && token ? (
                        <Button
                          onClick={() => setGitPanelOpen(true)}
                          variant="subtle"
                        >
                          <GitBranch aria-hidden="true" className="size-4" />
                          {t('agentTerminal.git.actions.open')}
                        </Button>
                      ) : null}
                      {selectedIsActive && connectionState === 'offline' ? (
                        <Button onClick={reconnectTerminal} variant="subtle">
                          <RefreshCw aria-hidden="true" className="size-4" />
                          {t('agentTerminal.actions.reconnect')}
                        </Button>
                      ) : null}
                      {selectedIsActive ? (
                        <Button
                          disabled={stopping}
                          onClick={() => void stopSession()}
                          variant="subtle"
                        >
                          <CircleStop aria-hidden="true" className="size-4" />
                          {t('agentTerminal.actions.stop')}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  <div className="min-h-0 flex-1">
                    {gitPanelDocked && token ? (
                      <Group className="h-full" orientation="horizontal">
                        <Panel
                          className="h-full min-h-0"
                          defaultSize="64%"
                          id="agent-terminal"
                          minSize="420px"
                        >
                          {terminalSurface}
                        </Panel>
                        <Separator
                          aria-label={t('agentTerminal.git.resizePanel')}
                          className="w-1 bg-app-border transition-colors hover:bg-app-accent focus-visible:bg-app-accent focus-visible:outline-none"
                          id="agent-terminal-git-separator"
                        />
                        <Panel
                          className="h-full min-h-0"
                          defaultSize="36%"
                          id="agent-terminal-git"
                          maxSize="65%"
                          minSize="320px"
                        >
                          <AgentTerminalGitPanel
                            rootKey={selectedSession.root_key}
                            token={token}
                          />
                        </Panel>
                      </Group>
                    ) : (
                      terminalSurface
                    )}
                  </div>
                </>
              ) : (
                <div className="grid h-full place-items-center p-6">
                  <EmptyState
                    title={t('agentTerminal.noSessionTitle')}
                    description={t('agentTerminal.noSessionDescription')}
                    action={{
                      label: t('agentTerminal.actions.newSession'),
                      onClick: () => void createSession(),
                    }}
                  />
                </div>
              )}
            </main>
          </div>
        )}

        <footer className="flex shrink-0 items-center gap-2 border-t border-app-border bg-app-surface px-4 py-2 app-text-caption text-app-ink/55">
          <ShieldAlert aria-hidden="true" className="size-4 shrink-0" />
          <span>{t('agentTerminal.securityNotice')}</span>
        </footer>
      </div>
      {selectedSession && token && !gitPanelDocked ? (
        <DetailDrawer
          contentClassName="w-[min(680px,100vw)] border-app-border bg-app-surface"
          description={t('agentTerminal.git.drawerDescription')}
          embedded
          onOpenChange={setGitPanelOpen}
          open={gitPanelOpen}
          title={t('agentTerminal.git.drawerTitle')}
        >
          <AgentTerminalGitPanel
            onClose={() => setGitPanelOpen(false)}
            rootKey={selectedSession.root_key}
            token={token}
          />
        </DetailDrawer>
      ) : null}
      {confirmDialog}
    </>
  );
}
