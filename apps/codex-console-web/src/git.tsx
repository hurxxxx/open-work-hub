import { Button } from '@open-work-hub/ui';
import { GitBranch, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type Detail, type GitState } from './api';
import { type Locale, type Translate } from './i18n';
import { Changes } from './views';

export function useGitState(task: Detail | null) {
  const [state, setState] = useState<GitState | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const sequence = useRef(0);
  const id = task?.id;
  const root = task?.root;
  const status = task?.status;
  const load = useCallback(async () => {
    if (!id) return;
    const current = ++sequence.current;
    setLoading(true);
    try {
      const next = await api<GitState>(`/tasks/${id}/git`);
      if (current !== sequence.current) return;
      setState(next);
      setFailed(false);
    } catch {
      if (current === sequence.current) {
        setState(null);
        setFailed(true);
      }
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }, [id, root]);
  useEffect(() => {
    setState(null);
    void load();
    const timer = window.setInterval(() => void load(), 10000);
    const visible = () => {
      if (!document.hidden) void load();
    };
    document.addEventListener('visibilitychange', visible);
    return () => {
      sequence.current++;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [load, status]);
  return { state, failed, loading, refresh: load };
}

export function GitSummary({
  state,
  t,
}: {
  state: GitState | null;
  t: Translate;
}) {
  if (!state) return null;
  return (
    <div className="git-summary" role="group" aria-label={t('Git workspace')}>
      <GitBranch size={14} aria-hidden="true" />
      <strong>{state.branch ?? t('Detached HEAD')}</strong>
      <span>
        {t('Changed files')} {state.changed}
      </span>
    </div>
  );
}

export function GitWorkspace({
  task,
  git,
  locale,
  t,
  onError,
}: {
  task: Detail;
  git: ReturnType<typeof useGitState>;
  locale: Locale;
  onError: (error: unknown) => void;
  t: Translate;
}) {
  const { state, failed, loading, refresh } = git;
  return (
    <div
      className="git-workspace stack"
      role="group"
      aria-label={t('Git workspace')}
    >
      <div className="git-summary">
        <h2>{t('Branch')}</h2>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('Refresh Git state')}
          disabled={loading}
          onClick={() => void refresh()}
        >
          <RefreshCw size={14} />
        </Button>
      </div>
      <code className="workspace-path">{task.root}</code>
      {state ? (
        <>
          <GitSummary state={state} t={t} />
          <code>{state.head ?? t('No commits')}</code>
          <span>
            {t('Staged')} {state.staged} · {t('Unstaged')} {state.unstaged} ·{' '}
            {t('Untracked')} {state.untracked}
          </span>
          {state.conflicts > 0 && (
            <span className="danger">
              {t('Conflicts')} {state.conflicts}
            </span>
          )}
          <span>
            {state.upstream
              ? `${state.upstream} · ↑${state.ahead ?? '?'} ↓${state.behind ?? '?'}`
              : t('No tracking branch')}
          </span>
          {state.detached && (
            <p>
              {t(
                'This workspace is based on a commit without a named branch. Your changes are preserved.',
              )}
            </p>
          )}
          <small>
            {t('Remote counts use local tracking refs; no automatic fetch.')} ·{' '}
            {t('Checked')}{' '}
            {new Date(state.checked_at).toLocaleTimeString(locale)}
          </small>
          <Changes
            key={`${task.id}:${task.root}`}
            task={task}
            refreshToken={state.checked_at}
            t={t}
            onError={onError}
          />
        </>
      ) : (
        <p role={failed ? 'alert' : undefined}>
          {t(failed ? 'Could not load Git state.' : 'Loading Git state…')}
        </p>
      )}
    </div>
  );
}
