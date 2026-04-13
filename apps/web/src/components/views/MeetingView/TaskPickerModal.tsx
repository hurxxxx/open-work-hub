import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { Loader2 } from 'lucide-react';
import { useParams } from 'react-router-dom';

import { useAuth } from '@/src/domains/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/domains/auth/auth-api';
import { NoAccessNotice } from '@/src/components/common/NoAccessNotice';
import {
  listPmsProjects,
  listProjectIssues,
  type PmsIssue,
  type PmsProject,
} from '@/src/domains/pms/pms-api';

interface TaskPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (issue: PmsIssue) => Promise<void> | void;
  excludeIssueIds?: string[];
}

export function TaskPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeIssueIds = [],
}: TaskPickerModalProps) {
  const { workspaceSlug } = useParams();
  const { token, user } = useAuth();
  const canAccessPms = hasWorkspaceMembership(user, workspaceSlug);
  const [projects, setProjects] = useState<PmsProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !token || !canAccessPms) return;
    setQuery('');
    setError(null);
    setSubmittingId(null);
    listPmsProjects(token)
      .then((response) => {
        setProjects(response.items);
        if (response.items.length > 0) {
          setSelectedProjectId(response.items[0].id);
        }
      })
      .catch((err: Error) => setError(err.message ?? '프로젝트 목록을 불러올 수 없습니다.'));
  }, [isOpen, token, canAccessPms]);

  useEffect(() => {
    if (!isOpen || !token || !canAccessPms || !selectedProjectId) {
      setIssues([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    listProjectIssues(token, selectedProjectId, { archived_state: 'active' })
      .then((response) => {
        if (cancelled) return;
        setIssues(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? '이슈를 불러올 수 없습니다.');
        setIssues([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token, canAccessPms, selectedProjectId]);

  const excludeSet = useMemo(() => new Set(excludeIssueIds), [excludeIssueIds]);

  const filteredIssues = useMemo(() => {
    const q = query.trim().toLowerCase();
    return issues
      .filter((issue) => !excludeSet.has(issue.id))
      .filter((issue) => {
        if (!q) return true;
        return issue.title.toLowerCase().includes(q);
      })
      .slice(0, 50);
  }, [issues, query, excludeSet]);

  async function handlePick(issue: PmsIssue) {
    setSubmittingId(issue.id);
    setError(null);
    try {
      await onPick(issue);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '이슈를 첨부할 수 없습니다.');
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="태스크 첨부"
      description="회의에 연결할 PMS 태스크를 선택합니다."
      maxWidth="max-w-xl"
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>닫기</Button>
        </div>
      }
    >
      <div className="space-y-4 text-app-ink">
        {!canAccessPms ? (
          <NoAccessNotice
            workspaceLabel="PMS 워크스페이스"
            action="태스크를 첨부"
          />
        ) : null}

        {canAccessPms && error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        {canAccessPms ? (
          <>
            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">프로젝트</label>
              <select
                value={selectedProjectId ?? ''}
                onChange={(e) => setSelectedProjectId(e.target.value || null)}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
              >
                {projects.length === 0 ? <option value="">프로젝트 없음</option> : null}
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.key} · {project.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="app-text-control-sm text-app-ink/70">검색</label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="이슈 제목으로 검색"
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
            </div>

            <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
              {loading ? (
                <div className="flex h-24 items-center justify-center text-app-ink/40">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              ) : filteredIssues.length === 0 ? (
                <div className="px-4 py-6 text-center app-text-caption text-app-ink/50">
                  표시할 이슈가 없습니다.
                </div>
              ) : (
                <ul className="divide-y divide-app-border">
                  {filteredIssues.map((issue) => (
                    <li key={issue.id}>
                      <button
                        type="button"
                        onClick={() => handlePick(issue)}
                        disabled={submittingId !== null}
                        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                      >
                        <div className="min-w-0">
                          <p className="app-text-body line-clamp-1 text-app-ink">
                            {issue.title}
                          </p>
                          <p className="app-text-caption text-app-ink/40">
                            {issue.reference} · {issue.status_label}
                          </p>
                        </div>
                        {submittingId === issue.id ? (
                          <Loader2 size={14} className="animate-spin text-app-ink/40" />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
