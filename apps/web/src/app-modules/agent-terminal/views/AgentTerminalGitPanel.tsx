import { Badge, Button, EmptyState, useFeedback } from '@open-work-hub/ui';
import { ChevronLeft, GitBranch, RefreshCw, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { UserDateTime } from '@/src/components/date/UserDateTime';

import {
  getAgentTerminalGitCommit,
  getAgentTerminalGitCommitDiff,
  getAgentTerminalGitDiff,
  getAgentTerminalGitHistory,
  getAgentTerminalGitStatus,
  getAgentTerminalGitSummary,
  type AgentTerminalGitChange,
  type AgentTerminalGitChangeScope,
  type AgentTerminalGitCommit,
  type AgentTerminalGitCommitDetail,
  type AgentTerminalGitCommitDiff,
  type AgentTerminalGitDiff,
  type AgentTerminalGitRef,
  type AgentTerminalGitStatus,
  type AgentTerminalGitSummary,
} from '../api/agent-terminal-api';
import {
  AgentTerminalGitDiffViewer,
  type AgentTerminalGitDiffSelection,
} from './AgentTerminalGitDiffViewer';
import { AgentTerminalGitSection } from './AgentTerminalGitSection';

const HISTORY_PAGE_SIZE = 50;
const SCOPE_ORDER: AgentTerminalGitChangeScope[] = [
  'conflicted',
  'staged',
  'unstaged',
  'untracked',
];

const KIND_MARK: Record<AgentTerminalGitChange['kind'], string> = {
  added: 'A',
  conflicted: '!',
  copied: 'C',
  deleted: 'D',
  modified: 'M',
  renamed: 'R',
  type_changed: 'T',
  untracked: 'U',
};

type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger';
type SelectedTarget =
  | { type: 'working'; key: string }
  | { type: 'commit'; sha: string }
  | null;

function changeKey(change: Pick<AgentTerminalGitChange, 'path' | 'scope'>) {
  return `${change.scope}\0${change.path}`;
}

function scopeTone(scope: AgentTerminalGitChangeScope): BadgeTone {
  if (scope === 'conflicted') return 'danger';
  if (scope === 'staged') return 'success';
  if (scope === 'untracked') return 'warning';
  return 'neutral';
}

function kindTone(kind: AgentTerminalGitChange['kind']): BadgeTone {
  if (kind === 'added') return 'success';
  if (kind === 'deleted' || kind === 'conflicted') return 'danger';
  if (kind === 'untracked') return 'warning';
  return 'neutral';
}

function sameWorktreeDiff(
  current: AgentTerminalGitDiff | null,
  next: AgentTerminalGitDiff,
) {
  return (
    current?.path === next.path &&
    current.scope === next.scope &&
    current.kind === next.kind &&
    current.old_path === next.old_path &&
    current.old_content === next.old_content &&
    current.new_content === next.new_content &&
    current.is_binary === next.is_binary &&
    current.too_large === next.too_large
  );
}

function RefRows({
  refs,
  showCurrent,
}: {
  refs: AgentTerminalGitRef[];
  showCurrent?: boolean;
}) {
  const { t } = useTranslation('apps');
  return (
    <div className="py-1">
      {refs.map((ref) => (
        <div
          className="flex items-center gap-2 px-3 py-1.5 text-app-ink/75"
          key={ref.full_name}
          title={ref.full_name}
        >
          <span className="min-w-0 flex-1 truncate font-mono text-xs">
            {ref.name}
          </span>
          {showCurrent && ref.current ? (
            <Badge tone="success">{t('agentTerminal.git.refs.current')}</Badge>
          ) : null}
          <span className="font-mono app-text-caption text-app-ink/40">
            {ref.target.slice(0, 8)}
          </span>
        </div>
      ))}
    </div>
  );
}

function LoadingRow({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-3 app-text-caption text-app-ink/45">
      <RefreshCw aria-hidden="true" className="size-3.5 animate-spin" />
      <span>{label}</span>
    </div>
  );
}

function CommitDetailView({
  commitSha,
  detail,
  failed,
  loading,
  onBack,
  onSelectPath,
  selectedPath,
}: {
  commitSha: string;
  detail: AgentTerminalGitCommitDetail | null;
  failed: boolean;
  loading: boolean;
  onBack: () => void;
  onSelectPath: (path: string) => void;
  selectedPath: string | null;
}) {
  const { t } = useTranslation('apps');

  return (
    <section
      aria-label={t('agentTerminal.git.sections.commitFiles')}
      className="min-h-full"
    >
      <header className="sticky top-0 z-10 border-b border-app-border bg-app-surface">
        <div className="px-2 py-1">
          <Button onClick={onBack} size="dense" variant="ghost">
            <ChevronLeft aria-hidden="true" className="size-3.5" />
            {t('agentTerminal.git.actions.backToHistory')}
          </Button>
        </div>
        <div className="px-3 pb-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-mono text-[11px] text-app-accent">
              {commitSha.slice(0, 8)}
            </span>
            {detail && (detail.parents ?? []).length > 1 ? (
              <Badge tone="neutral">
                {t('agentTerminal.git.history.merge')}
              </Badge>
            ) : null}
          </div>
          {detail ? (
            <>
              <p className="mt-1 break-words text-xs font-medium text-app-ink/80">
                {detail.subject || t('agentTerminal.git.history.noSubject')}
              </p>
              <p className="mt-1 truncate app-text-caption text-app-ink/45">
                {detail.author_name} ·{' '}
                <UserDateTime display="relative" value={detail.authored_at} />
              </p>
              {(detail.parents ?? []).length > 1 ? (
                <p className="mt-1 app-text-caption text-app-ink/45">
                  {t('agentTerminal.git.commitFiles.firstParent')}
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </header>

      {loading ? (
        <LoadingRow label={t('agentTerminal.git.commitFiles.loading')} />
      ) : failed ? (
        <p className="px-3 py-3 app-text-caption text-app-danger">
          {t('agentTerminal.git.commitFiles.loadFailed')}
        </p>
      ) : detail ? (
        <>
          <div className="flex items-center justify-between border-b border-app-border bg-app-bg px-3 py-1.5 app-text-caption font-semibold text-app-ink/55">
            <span>{t('agentTerminal.git.sections.commitFiles')}</span>
            <span>{detail.files?.length ?? 0}</span>
          </div>
          <div className="py-1">
            {(detail.files ?? []).map((file) => {
              const selected = file.path === selectedPath;
              return (
                <button
                  aria-current={selected ? 'true' : undefined}
                  className={`flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-app-surface-hover ${
                    selected ? 'bg-app-accent/10' : ''
                  }`}
                  key={`${file.old_path ?? ''}\0${file.path}`}
                  onClick={() => onSelectPath(file.path)}
                  title={
                    file.old_path
                      ? `${file.old_path} → ${file.path}`
                      : file.path
                  }
                  type="button"
                >
                  <Badge
                    aria-label={t(`agentTerminal.git.kind.${file.kind}`)}
                    className="min-w-6 justify-center px-1"
                    tone={kindTone(file.kind)}
                  >
                    {KIND_MARK[file.kind]}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-app-ink/75">
                    {file.path}
                  </span>
                </button>
              );
            })}
          </div>
          {detail.files_truncated ? (
            <p className="border-t border-app-border px-3 py-2 app-text-caption text-app-ink/55">
              {t('agentTerminal.git.commitFiles.truncated')}
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

export function AgentTerminalGitPanel({
  onClose,
  rootKey,
  token,
}: {
  onClose?: () => void;
  rootKey: string;
  token: string;
}) {
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const [gitStatus, setGitStatus] = useState<AgentTerminalGitStatus | null>(
    null,
  );
  const [summary, setSummary] = useState<AgentTerminalGitSummary | null>(null);
  const [history, setHistory] = useState<AgentTerminalGitCommit[]>([]);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [repositoryLoading, setRepositoryLoading] = useState(true);
  const [historyLoadingMore, setHistoryLoadingMore] = useState(false);
  const [statusFailed, setStatusFailed] = useState(false);
  const [repositoryFailed, setRepositoryFailed] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<SelectedTarget>(null);
  const [worktreeDiff, setWorktreeDiff] = useState<AgentTerminalGitDiff | null>(
    null,
  );
  const [worktreeDiffLoading, setWorktreeDiffLoading] = useState(false);
  const [worktreeDiffFailed, setWorktreeDiffFailed] = useState(false);
  const [commitDetail, setCommitDetail] =
    useState<AgentTerminalGitCommitDetail | null>(null);
  const [commitDetailLoading, setCommitDetailLoading] = useState(false);
  const [commitDetailFailed, setCommitDetailFailed] = useState(false);
  const [selectedCommitPath, setSelectedCommitPath] = useState<string | null>(
    null,
  );
  const [commitDiff, setCommitDiff] =
    useState<AgentTerminalGitCommitDiff | null>(null);
  const [commitDiffLoading, setCommitDiffLoading] = useState(false);
  const [commitDiffFailed, setCommitDiffFailed] = useState(false);
  const [refreshSequence, setRefreshSequence] = useState(0);
  const statusRequestRef = useRef(0);
  const repositoryRequestRef = useRef(0);
  const historyMoreRequestRef = useRef(0);
  const worktreeDiffRequestRef = useRef(0);
  const commitDetailRequestRef = useRef(0);
  const commitDiffRequestRef = useRef(0);
  const lastDiffFailureRef = useRef<string | null>(null);
  const navigationScrollRef = useRef<HTMLDivElement>(null);
  const historyScrollTopRef = useRef(0);
  const observedHeadRef = useRef<string | undefined>(undefined);

  const loadStatus = useCallback(
    async (notifyOnFailure: boolean) => {
      const requestId = ++statusRequestRef.current;
      setStatusLoading(true);
      try {
        const next = await getAgentTerminalGitStatus(token, rootKey);
        if (requestId !== statusRequestRef.current) return;
        const changes = next.changes ?? [];
        setGitStatus(next);
        setStatusFailed(false);
        setSelectedTarget((current) => {
          if (current?.type === 'commit') return current;
          if (
            current?.type === 'working' &&
            changes.some((change) => changeKey(change) === current.key)
          ) {
            return current;
          }
          return changes[0]
            ? { type: 'working', key: changeKey(changes[0]) }
            : null;
        });
        setRefreshSequence((current) => current + 1);
      } catch {
        if (requestId !== statusRequestRef.current) return;
        setStatusFailed(true);
        if (notifyOnFailure) {
          feedback.error(t('agentTerminal.git.feedback.statusFailed'));
        }
      } finally {
        if (requestId === statusRequestRef.current) {
          setStatusLoading(false);
        }
      }
    },
    [feedback, rootKey, t, token],
  );

  const loadRepository = useCallback(
    async (notifyOnFailure: boolean) => {
      const requestId = ++repositoryRequestRef.current;
      setRepositoryLoading(true);
      try {
        const [nextSummary, nextHistory] = await Promise.all([
          getAgentTerminalGitSummary(token, rootKey),
          getAgentTerminalGitHistory(token, rootKey, {
            limit: HISTORY_PAGE_SIZE,
            offset: 0,
          }),
        ]);
        if (requestId !== repositoryRequestRef.current) return;
        setSummary(nextSummary);
        setHistory(nextHistory.items ?? []);
        setHistoryHasMore(nextHistory.has_more);
        setRepositoryFailed(false);
      } catch {
        if (requestId !== repositoryRequestRef.current) return;
        setRepositoryFailed(true);
        if (notifyOnFailure) {
          feedback.error(t('agentTerminal.git.feedback.repositoryFailed'));
        }
      } finally {
        if (requestId === repositoryRequestRef.current) {
          setRepositoryLoading(false);
        }
      }
    },
    [feedback, rootKey, t, token],
  );

  useEffect(() => {
    setGitStatus(null);
    setSummary(null);
    setHistory([]);
    setHistoryHasMore(false);
    setSelectedTarget(null);
    setWorktreeDiff(null);
    setCommitDetail(null);
    setCommitDiff(null);
    setStatusFailed(false);
    setRepositoryFailed(false);
    observedHeadRef.current = undefined;
    void loadStatus(false);
    void loadRepository(false);
    const timer = window.setInterval(() => {
      void loadStatus(false);
    }, 5000);
    return () => {
      window.clearInterval(timer);
      statusRequestRef.current += 1;
      repositoryRequestRef.current += 1;
      historyMoreRequestRef.current += 1;
    };
  }, [loadRepository, loadStatus]);

  useEffect(() => {
    if (!gitStatus?.is_repository) return;
    const identity = `${gitStatus.branch ?? '(detached)'}:${gitStatus.head ?? '(unborn)'}`;
    if (observedHeadRef.current === undefined) {
      observedHeadRef.current = identity;
      return;
    }
    if (observedHeadRef.current !== identity) {
      observedHeadRef.current = identity;
      void loadRepository(false);
    }
  }, [
    gitStatus?.branch,
    gitStatus?.head,
    gitStatus?.is_repository,
    loadRepository,
  ]);

  const loadMoreHistory = useCallback(async () => {
    if (historyLoadingMore || !historyHasMore) return;
    const requestId = ++historyMoreRequestRef.current;
    setHistoryLoadingMore(true);
    try {
      const next = await getAgentTerminalGitHistory(token, rootKey, {
        limit: HISTORY_PAGE_SIZE,
        offset: history.length,
      });
      if (requestId !== historyMoreRequestRef.current) return;
      setHistory((current) => {
        const known = new Set(current.map((commit) => commit.sha));
        return [
          ...current,
          ...(next.items ?? []).filter((commit) => !known.has(commit.sha)),
        ];
      });
      setHistoryHasMore(next.has_more);
    } catch {
      if (requestId !== historyMoreRequestRef.current) return;
      feedback.error(t('agentTerminal.git.feedback.historyFailed'));
    } finally {
      if (requestId === historyMoreRequestRef.current) {
        setHistoryLoadingMore(false);
      }
    }
  }, [
    feedback,
    history.length,
    historyHasMore,
    historyLoadingMore,
    rootKey,
    t,
    token,
  ]);

  const selectedChange = useMemo(() => {
    if (selectedTarget?.type !== 'working') return null;
    return (
      (gitStatus?.changes ?? []).find(
        (change) => changeKey(change) === selectedTarget.key,
      ) ?? null
    );
  }, [gitStatus?.changes, selectedTarget]);

  useEffect(() => {
    if (!selectedChange) {
      setWorktreeDiff(null);
      setWorktreeDiffFailed(false);
      setWorktreeDiffLoading(false);
      return;
    }
    const requestId = ++worktreeDiffRequestRef.current;
    const requestKey = changeKey(selectedChange);
    setWorktreeDiffLoading(true);
    setWorktreeDiffFailed(false);
    void getAgentTerminalGitDiff(token, rootKey, selectedChange)
      .then((next) => {
        if (requestId !== worktreeDiffRequestRef.current) return;
        setWorktreeDiff((current) =>
          sameWorktreeDiff(current, next) ? current : next,
        );
        lastDiffFailureRef.current = null;
      })
      .catch(() => {
        if (requestId !== worktreeDiffRequestRef.current) return;
        setWorktreeDiffFailed(true);
        if (lastDiffFailureRef.current !== requestKey) {
          feedback.error(t('agentTerminal.git.feedback.diffFailed'));
          lastDiffFailureRef.current = requestKey;
        }
      })
      .finally(() => {
        if (requestId === worktreeDiffRequestRef.current) {
          setWorktreeDiffLoading(false);
        }
      });
    return () => {
      worktreeDiffRequestRef.current += 1;
    };
  }, [feedback, refreshSequence, rootKey, selectedChange, t, token]);

  useEffect(() => {
    if (selectedTarget?.type !== 'commit') {
      setCommitDetail(null);
      setSelectedCommitPath(null);
      setCommitDetailFailed(false);
      setCommitDetailLoading(false);
      return;
    }
    const requestId = ++commitDetailRequestRef.current;
    setCommitDetail(null);
    setSelectedCommitPath(null);
    setCommitDetailLoading(true);
    setCommitDetailFailed(false);
    void getAgentTerminalGitCommit(token, rootKey, selectedTarget.sha)
      .then((next) => {
        if (requestId !== commitDetailRequestRef.current) return;
        setCommitDetail(next);
        setSelectedCommitPath(next.files?.[0]?.path ?? null);
      })
      .catch(() => {
        if (requestId !== commitDetailRequestRef.current) return;
        setCommitDetailFailed(true);
        feedback.error(t('agentTerminal.git.feedback.commitFailed'));
      })
      .finally(() => {
        if (requestId === commitDetailRequestRef.current) {
          setCommitDetailLoading(false);
        }
      });
    return () => {
      commitDetailRequestRef.current += 1;
    };
  }, [feedback, rootKey, selectedTarget, t, token]);

  const selectedCommitFile = useMemo(
    () =>
      (commitDetail?.files ?? []).find(
        (file) => file.path === selectedCommitPath,
      ) ?? null,
    [commitDetail?.files, selectedCommitPath],
  );

  useEffect(() => {
    if (!commitDetail || !selectedCommitFile) {
      setCommitDiff(null);
      setCommitDiffFailed(false);
      setCommitDiffLoading(false);
      return;
    }
    const requestId = ++commitDiffRequestRef.current;
    setCommitDiff(null);
    setCommitDiffLoading(true);
    setCommitDiffFailed(false);
    void getAgentTerminalGitCommitDiff(
      token,
      rootKey,
      commitDetail.sha,
      selectedCommitFile.path,
    )
      .then((next) => {
        if (requestId !== commitDiffRequestRef.current) return;
        setCommitDiff(next);
      })
      .catch(() => {
        if (requestId !== commitDiffRequestRef.current) return;
        setCommitDiffFailed(true);
        feedback.error(t('agentTerminal.git.feedback.diffFailed'));
      })
      .finally(() => {
        if (requestId === commitDiffRequestRef.current) {
          setCommitDiffLoading(false);
        }
      });
    return () => {
      commitDiffRequestRef.current += 1;
    };
  }, [commitDetail, feedback, rootKey, selectedCommitFile, t, token]);

  const groupedChanges = useMemo(
    () =>
      SCOPE_ORDER.map((scope) => ({
        scope,
        items: (gitStatus?.changes ?? []).filter(
          (change) => change.scope === scope,
        ),
      })).filter((group) => group.items.length > 0),
    [gitStatus?.changes],
  );
  const refs = summary?.refs ?? [];
  const localBranches = refs.filter((ref) => ref.kind === 'local_branch');
  const remoteBranches = refs.filter((ref) => ref.kind === 'remote_branch');
  const tags = refs.filter((ref) => ref.kind === 'tag');
  const stashes = summary?.stashes ?? [];
  const changeCount = gitStatus?.changes?.length ?? 0;
  const headLabel = gitStatus?.branch
    ? gitStatus.branch
    : gitStatus?.head
      ? t('agentTerminal.git.detachedHead', {
          head: gitStatus.head.slice(0, 8),
        })
      : t('agentTerminal.git.unknownHead');

  const selectedWorktreeDiff =
    worktreeDiff &&
    selectedChange &&
    worktreeDiff.path === selectedChange.path &&
    worktreeDiff.scope === selectedChange.scope
      ? worktreeDiff
      : null;
  const selectedCommitDiff =
    commitDiff &&
    commitDetail &&
    selectedCommitFile &&
    commitDiff.commit === commitDetail.sha &&
    commitDiff.path === selectedCommitFile.path
      ? commitDiff
      : null;

  let diffSelection: AgentTerminalGitDiffSelection | null = null;
  if (selectedChange) {
    diffSelection = {
      badgeLabel: t(`agentTerminal.git.scope.${selectedChange.scope}`),
      badgeTone: scopeTone(selectedChange.scope),
      contextLabel: t('agentTerminal.git.diff.workingTreeContext', {
        branch: headLabel,
      }),
      key: `working:${selectedChange.scope}:${selectedChange.path}`,
      kind: selectedChange.kind,
      oldPath: selectedChange.old_path,
      path: selectedChange.path,
    };
  } else if (commitDetail && selectedCommitFile) {
    diffSelection = {
      badgeLabel: t(`agentTerminal.git.kind.${selectedCommitFile.kind}`),
      badgeTone: kindTone(selectedCommitFile.kind),
      contextLabel: t('agentTerminal.git.diff.commitContext', {
        commit: commitDetail.sha.slice(0, 8),
        subject: commitDetail.subject,
      }),
      key: `commit:${commitDetail.sha}:${selectedCommitFile.path}`,
      kind: selectedCommitFile.kind,
      oldPath: selectedCommitFile.old_path,
      path: selectedCommitFile.path,
    };
  }

  const refreshAll = () => {
    void loadStatus(true);
    void loadRepository(true);
  };

  const selectCommit = (sha: string) => {
    historyScrollTopRef.current = navigationScrollRef.current?.scrollTop ?? 0;
    setSelectedTarget({ type: 'commit', sha });
    window.requestAnimationFrame(() => {
      if (navigationScrollRef.current) {
        navigationScrollRef.current.scrollTop = 0;
      }
    });
  };

  const returnToHistory = () => {
    setSelectedTarget(null);
    window.requestAnimationFrame(() => {
      if (navigationScrollRef.current) {
        navigationScrollRef.current.scrollTop = historyScrollTopRef.current;
      }
    });
  };

  return (
    <section className="flex h-full min-h-0 flex-col bg-app-surface text-app-ink">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-app-border px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <GitBranch aria-hidden="true" className="size-4 text-app-accent" />
            <h2 className="truncate app-text-label">
              {t('agentTerminal.git.title', { count: changeCount })}
            </h2>
          </div>
          {gitStatus?.is_repository ? (
            <p className="mt-0.5 truncate app-text-caption text-app-ink/50">
              {headLabel}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            aria-label={t('agentTerminal.git.actions.refresh')}
            disabled={statusLoading || repositoryLoading}
            onClick={refreshAll}
            size="icon"
            title={t('agentTerminal.git.actions.refresh')}
            variant="ghost"
          >
            <RefreshCw
              aria-hidden="true"
              className={`size-4 ${
                statusLoading || repositoryLoading ? 'animate-spin' : ''
              }`}
            />
          </Button>
          {onClose ? (
            <Button
              aria-label={t('agentTerminal.git.actions.close')}
              onClick={onClose}
              size="icon"
              title={t('agentTerminal.git.actions.close')}
              variant="ghost"
            >
              <X aria-hidden="true" className="size-4" />
            </Button>
          ) : null}
        </div>
      </header>

      {statusLoading && !gitStatus ? (
        <div className="grid min-h-0 flex-1 place-items-center text-app-ink/45">
          <RefreshCw aria-hidden="true" className="size-5 animate-spin" />
          <span className="sr-only">{t('agentTerminal.git.loading')}</span>
        </div>
      ) : statusFailed && !gitStatus ? (
        <div className="p-3">
          <EmptyState
            action={{
              label: t('agentTerminal.actions.retry'),
              onClick: refreshAll,
            }}
            description={t('agentTerminal.git.loadFailedDescription')}
            title={t('agentTerminal.git.loadFailedTitle')}
          />
        </div>
      ) : gitStatus && !gitStatus.is_repository ? (
        <div className="p-3">
          <EmptyState
            description={t('agentTerminal.git.notRepositoryDescription')}
            title={t('agentTerminal.git.notRepositoryTitle')}
          />
        </div>
      ) : (
        <>
          <div
            className="ui-scrollbar max-h-[52%] min-h-[160px] shrink-0 overflow-y-auto border-b border-app-border"
            ref={navigationScrollRef}
          >
            {selectedTarget?.type === 'commit' ? (
              <CommitDetailView
                commitSha={selectedTarget.sha}
                detail={commitDetail}
                failed={commitDetailFailed}
                loading={commitDetailLoading}
                onBack={returnToHistory}
                onSelectPath={setSelectedCommitPath}
                selectedPath={selectedCommitPath}
              />
            ) : null}
            <AgentTerminalGitSection
              hidden={selectedTarget?.type === 'commit'}
              title={t('agentTerminal.git.sections.repository')}
            >
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 px-3 py-2 app-text-caption">
                <dt className="text-app-ink/45">
                  {t('agentTerminal.git.repository.branch')}
                </dt>
                <dd className="truncate font-mono text-app-ink/75">
                  {headLabel}
                </dd>
                <dt className="text-app-ink/45">
                  {t('agentTerminal.git.repository.head')}
                </dt>
                <dd className="truncate font-mono text-app-ink/75">
                  {gitStatus?.head?.slice(0, 12) ?? '—'}
                </dd>
                <dt className="text-app-ink/45">
                  {t('agentTerminal.git.repository.upstream')}
                </dt>
                <dd className="truncate font-mono text-app-ink/75">
                  {gitStatus?.upstream ??
                    t('agentTerminal.git.repository.none')}
                </dd>
                <dt className="text-app-ink/45">
                  {t('agentTerminal.git.repository.sync')}
                </dt>
                <dd className="text-app-ink/75">
                  {t('agentTerminal.git.repository.aheadBehind', {
                    ahead: gitStatus?.ahead ?? 0,
                    behind: gitStatus?.behind ?? 0,
                  })}
                </dd>
              </dl>
            </AgentTerminalGitSection>

            <AgentTerminalGitSection
              hidden={selectedTarget?.type === 'commit'}
              count={changeCount}
              title={t('agentTerminal.git.sections.changes')}
            >
              {changeCount === 0 ? (
                <p className="px-3 py-3 app-text-caption text-app-ink/50">
                  {t('agentTerminal.git.cleanDescription')}
                </p>
              ) : (
                groupedChanges.map((group) => (
                  <div key={group.scope}>
                    <div className="flex items-center justify-between border-y border-app-border bg-app-bg px-3 py-1 app-text-caption font-semibold text-app-ink/55 first:border-t-0">
                      <span>{t(`agentTerminal.git.scope.${group.scope}`)}</span>
                      <span>{group.items.length}</span>
                    </div>
                    <div className="py-1">
                      {group.items.map((change) => {
                        const key = changeKey(change);
                        const selected =
                          selectedTarget?.type === 'working' &&
                          key === selectedTarget.key;
                        return (
                          <button
                            aria-current={selected ? 'true' : undefined}
                            className={`flex w-full items-center gap-2 px-3 py-1.5 text-left transition-colors hover:bg-app-surface-hover ${
                              selected
                                ? 'bg-app-accent/10 text-app-ink'
                                : 'text-app-ink/75'
                            }`}
                            key={key}
                            onClick={() => {
                              lastDiffFailureRef.current = null;
                              setSelectedTarget({ type: 'working', key });
                            }}
                            title={
                              change.old_path
                                ? `${change.old_path} → ${change.path}`
                                : change.path
                            }
                            type="button"
                          >
                            <Badge
                              aria-label={t(
                                `agentTerminal.git.kind.${change.kind}`,
                              )}
                              className="min-w-6 justify-center px-1"
                              tone={scopeTone(change.scope)}
                            >
                              {KIND_MARK[change.kind]}
                            </Badge>
                            <span className="min-w-0 flex-1 truncate font-mono text-xs">
                              {change.path}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
              {gitStatus?.truncated ? (
                <p className="border-t border-app-border px-3 py-2 app-text-caption text-app-ink/55">
                  {t('agentTerminal.git.truncated')}
                </p>
              ) : null}
            </AgentTerminalGitSection>

            <AgentTerminalGitSection
              hidden={selectedTarget?.type === 'commit'}
              count={history.length}
              title={t('agentTerminal.git.sections.history')}
            >
              {repositoryLoading && history.length === 0 ? (
                <LoadingRow label={t('agentTerminal.git.history.loading')} />
              ) : repositoryFailed && history.length === 0 ? (
                <p className="px-3 py-3 app-text-caption text-app-danger">
                  {t('agentTerminal.git.history.loadFailed')}
                </p>
              ) : history.length === 0 ? (
                <p className="px-3 py-3 app-text-caption text-app-ink/50">
                  {t('agentTerminal.git.history.empty')}
                </p>
              ) : (
                <div className="py-1">
                  {history.map((commit) => {
                    const selected =
                      selectedTarget?.type === 'commit' &&
                      selectedTarget.sha === commit.sha;
                    return (
                      <button
                        aria-current={selected ? 'true' : undefined}
                        className={`block w-full px-3 py-2 text-left transition-colors hover:bg-app-surface-hover ${
                          selected ? 'bg-app-accent/10' : ''
                        }`}
                        key={commit.sha}
                        onClick={() => selectCommit(commit.sha)}
                        title={`${commit.sha} · ${commit.subject}`}
                        type="button"
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="shrink-0 font-mono text-[11px] text-app-accent">
                            {commit.sha.slice(0, 8)}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-xs font-medium text-app-ink/80">
                            {commit.subject ||
                              t('agentTerminal.git.history.noSubject')}
                          </span>
                          {(commit.parents ?? []).length > 1 ? (
                            <Badge tone="neutral">
                              {t('agentTerminal.git.history.merge')}
                            </Badge>
                          ) : null}
                        </div>
                        <p className="mt-1 truncate app-text-caption text-app-ink/45">
                          {commit.author_name} ·{' '}
                          <UserDateTime
                            display="relative"
                            value={commit.authored_at}
                          />
                        </p>
                      </button>
                    );
                  })}
                  {historyHasMore ? (
                    <div className="border-t border-app-border p-2">
                      <Button
                        className="w-full"
                        disabled={historyLoadingMore}
                        onClick={() => void loadMoreHistory()}
                        size="dense"
                        variant="ghost"
                      >
                        {historyLoadingMore
                          ? t('agentTerminal.git.history.loadingMore')
                          : t('agentTerminal.git.history.loadMore')}
                      </Button>
                    </div>
                  ) : null}
                </div>
              )}
            </AgentTerminalGitSection>

            <AgentTerminalGitSection
              hidden={selectedTarget?.type === 'commit'}
              count={localBranches.length + remoteBranches.length}
              defaultOpen={false}
              title={t('agentTerminal.git.sections.branches')}
            >
              {repositoryLoading && !summary ? (
                <LoadingRow label={t('agentTerminal.git.refs.loading')} />
              ) : localBranches.length + remoteBranches.length === 0 ? (
                <p className="px-3 py-3 app-text-caption text-app-ink/50">
                  {t('agentTerminal.git.refs.branchesEmpty')}
                </p>
              ) : (
                <>
                  {localBranches.length > 0 ? (
                    <>
                      <p className="border-b border-app-border bg-app-bg px-3 py-1 app-text-caption font-semibold text-app-ink/50">
                        {t('agentTerminal.git.refs.localBranches')}
                      </p>
                      <RefRows refs={localBranches} showCurrent />
                    </>
                  ) : null}
                  {remoteBranches.length > 0 ? (
                    <>
                      <p className="border-y border-app-border bg-app-bg px-3 py-1 app-text-caption font-semibold text-app-ink/50">
                        {t('agentTerminal.git.refs.remoteBranches')}
                      </p>
                      <RefRows refs={remoteBranches} />
                    </>
                  ) : null}
                  <p className="border-t border-app-border px-3 py-2 app-text-caption text-app-ink/45">
                    {t('agentTerminal.git.refs.readOnly')}
                  </p>
                </>
              )}
            </AgentTerminalGitSection>

            <AgentTerminalGitSection
              hidden={selectedTarget?.type === 'commit'}
              count={tags.length}
              defaultOpen={false}
              title={t('agentTerminal.git.sections.tags')}
            >
              {tags.length > 0 ? (
                <RefRows refs={tags} />
              ) : (
                <p className="px-3 py-3 app-text-caption text-app-ink/50">
                  {t('agentTerminal.git.refs.tagsEmpty')}
                </p>
              )}
            </AgentTerminalGitSection>

            <AgentTerminalGitSection
              hidden={selectedTarget?.type === 'commit'}
              count={stashes.length}
              defaultOpen={false}
              title={t('agentTerminal.git.sections.stashes')}
            >
              {stashes.length > 0 ? (
                <div className="py-1">
                  {stashes.map((stash) => (
                    <div className="px-3 py-1.5" key={stash.sha}>
                      <div className="flex items-center gap-2">
                        <span className="shrink-0 font-mono text-[11px] text-app-accent">
                          {stash.ref}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-xs text-app-ink/75">
                          {stash.subject}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="px-3 py-3 app-text-caption text-app-ink/50">
                  {t('agentTerminal.git.refs.stashesEmpty')}
                </p>
              )}
              {summary?.refs_truncated || summary?.stashes_truncated ? (
                <p className="border-t border-app-border px-3 py-2 app-text-caption text-app-ink/55">
                  {t('agentTerminal.git.refs.truncated')}
                </p>
              ) : null}
            </AgentTerminalGitSection>
          </div>

          <AgentTerminalGitDiffViewer
            diff={
              selectedTarget?.type === 'working'
                ? selectedWorktreeDiff
                : selectedCommitDiff
            }
            failed={
              selectedTarget?.type === 'working'
                ? worktreeDiffFailed
                : commitDetailFailed || commitDiffFailed
            }
            loading={
              selectedTarget?.type === 'working'
                ? worktreeDiffLoading
                : commitDetailLoading || commitDiffLoading
            }
            selection={diffSelection}
          />
        </>
      )}
    </section>
  );
}
