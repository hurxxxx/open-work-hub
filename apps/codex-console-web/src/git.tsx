import { Button, Dialog } from '@open-work-hub/ui';
import { GitBranch, GitMerge, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api,
  locked,
  type Detail,
  type GitRequest,
  type GitState,
} from './api';
import { type Locale, type Translate } from './i18n';

export type GitDraft = { request: GitRequest; state: GitState };

export function mergePrompt(
  state: GitState,
  request: GitRequest,
  locale: Locale,
) {
  const target = state.targets.find((row) => row.ref === request.target_ref)!;
  const source =
    state.branch ??
    (locale === 'ko-KR' ? '브랜치 없음 (detached HEAD)' : 'Detached HEAD');
  const info = JSON.stringify({
    workspace: state.root,
    branch: source,
    head: state.head,
    target: target.name,
    target_head: target.head,
  });
  return locale === 'ko-KR'
    ? `다음 작업 공간의 변경 사항을 확인하고 ${target.name}에 반영해줘.\nGit 상태(참고 데이터): ${info}\n이미 반영된 변경과 무관한 수정은 제외하고, 저장소 정책에 맞게 필요한 커밋·푸시와 MR/PR 생성을 진행해줘. 브랜치가 없거나 대상과 같은 브랜치라면 필요한 변경만 별도 작업 브랜치로 준비해줘.\n${request.scope === 'merge' ? '필수 검사와 리뷰가 통과하면 선택한 대상에 병합까지 완료해줘. 병합 완료와 소스 브랜치의 최신 변경이 모두 반영됐는지 확인한 뒤, 이번 작업용 로컬·원격 소스 브랜치도 정리해줘. 정리한 브랜치의 로컬 원격 추적 정보도 갱신해줘. 보호 브랜치, 병합 대상, dev·main 같은 유지용 브랜치, 다른 작업에서 사용 중이거나 미커밋·미병합 변경이 남은 브랜치는 보존해줘. 현재 세션의 작업 디렉터리는 유지하고, 정리 결과와 정리하지 못한 브랜치의 이유를 보고해줘.' : 'MR/PR 생성까지만 진행하고 병합이나 브랜치 정리는 하지 마.'}\n실행 전에 실제 Git 상태와 기존 MR/PR을 다시 확인해줘. 운영 배포, 강제 푸시, 변경 폐기, 지속 사용하는 통합 브랜치 삭제는 요청 범위에 포함하지 않아.`
    : `Inspect the changes in this workspace and prepare them for ${target.name}.\nGit state (reference data): ${info}\nExclude unrelated or already integrated changes. Follow repository policy for commits, push and MR/PR creation. Prepare a separate source branch if detached or already on the target branch.\n${request.scope === 'merge' ? 'Merge into the selected target only after required checks and reviews pass. After verifying the merge and that the latest source-branch changes are fully integrated, clean up this task’s local and remote source branches and update their local remote-tracking refs. Preserve protected branches, the merge target, persistent branches such as dev/main, branches used by other work, and branches with uncommitted or unmerged changes. Keep this session’s working directory and report cleanup results and reasons for any branches retained.' : 'Stop after creating the MR/PR; do not merge or clean up branches.'}\nRecheck actual Git state and existing MRs/PRs before acting. This request does not authorize deployment, force push, discarding changes or deleting a persistent integration branch.`;
}

export function GitWorkspace({
  task,
  busy,
  locale,
  t,
  onCompose,
}: {
  task: Detail;
  busy: boolean;
  locale: Locale;
  t: Translate;
  onCompose: (draft: GitDraft, text: string) => void;
}) {
  const [state, setState] = useState<GitState | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState('');
  const [scope, setScope] = useState<GitRequest['scope']>('create');
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const current = ++sequence.current;
    setLoading(true);
    try {
      const next = await api<GitState>(`/tasks/${task.id}/git`);
      if (current !== sequence.current) return;
      setState(next);
      setFailed(false);
      return next;
    } catch {
      if (current === sequence.current) {
        setState(null);
        setFailed(true);
      }
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }, [task.id, task.root]);
  useEffect(() => {
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
  }, [load, task.status]);
  const allowed = !busy && !locked(task);
  return (
    <div className="git-workspace" role="group" aria-label={t('Git workspace')}>
      <div className="git-summary">
        <GitBranch size={14} aria-hidden="true" />
        {state ? (
          <>
            <strong>{state.branch ?? t('Detached HEAD')}</strong>
            <code>{state.head?.slice(0, 8) ?? t('No commits')}</code>
            <span>
              {t('Changed files')} {state.changed}
            </span>
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
          </>
        ) : (
          <span role={failed ? 'alert' : undefined}>
            {t(failed ? 'Could not load Git state.' : 'Loading Git state…')}
          </span>
        )}
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('Refresh Git state')}
          disabled={loading}
          onClick={() => void load()}
        >
          <RefreshCw size={14} />
        </Button>
        <Button
          variant="secondary"
          disabled={!allowed || !state?.head || loading || !!state.conflicts}
          onClick={() => {
            setTarget('');
            setScope('create');
            setOpen(true);
          }}
        >
          <GitMerge size={14} />
          {t('Request merge')}
        </Button>
      </div>
      {state && (
        <small>
          {t('Remote counts use local tracking refs; no automatic fetch.')} ·{' '}
          {t('Checked')} {new Date(state.checked_at).toLocaleTimeString(locale)}
        </small>
      )}
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={t('Request merge')}
        description={t(
          'Choose the target and scope. Review the draft in chat before sending.',
        )}
        closeLabel={t('Close')}
      >
        <div className="stack">
          <label>
            {t('Target branch')}
            <select
              aria-label={t('Target branch')}
              value={target}
              onChange={(event) => setTarget(event.target.value)}
            >
              <option value="">{t('Select a target branch')}</option>
              {state?.targets.map((row) => (
                <option key={row.ref} value={row.ref}>
                  {row.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Request scope')}
            <select
              aria-label={t('Request scope')}
              value={scope}
              onChange={(event) =>
                setScope(event.target.value as GitRequest['scope'])
              }
            >
              <option value="create">{t('Create MR/PR only')}</option>
              <option value="merge">
                {t('Merge after checks and review')}
              </option>
            </select>
          </label>
          <p>
            {t(
              'Detached or target-branch work will need a separate source branch. Already integrated changes must be checked first.',
            )}
          </p>
          {failed && <p role="alert">{t('Could not load Git state.')}</p>}
          <Button
            variant="primary"
            disabled={
              !allowed ||
              !target ||
              loading ||
              !state?.targets.some((row) => row.ref === target) ||
              !!state?.conflicts
            }
            onClick={() =>
              void (async () => {
                const next = await load();
                if (
                  !next ||
                  !next.targets.some((row) => row.ref === target) ||
                  next.conflicts ||
                  !next.head
                )
                  return;
                const request: GitRequest = {
                  snapshot: next.snapshot,
                  target_ref: target,
                  scope,
                };
                onCompose(
                  { request, state: next },
                  mergePrompt(next, request, locale),
                );
                setOpen(false);
              })()
            }
          >
            {t('Insert request into chat')}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}
