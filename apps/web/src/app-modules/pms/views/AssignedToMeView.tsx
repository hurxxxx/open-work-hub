import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Loader2 } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  getIssueDetail,
  listAssignedIssues,
  listPmsTaskLists,
  type PmsIssue,
  type PmsTaskList,
} from '../api/pms-api';
import { taskListRoleAllows } from '../api/pms-permissions';
import { ListView } from './ListView';
import { TaskDetail } from './TaskDetail';

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export const AssignedToMeView = ({
  workspaceSlug: workspaceSlugProp = null,
}: {
  workspaceSlug?: string | null;
}) => {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const { workspaceSlug: routeWorkspaceSlug } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const workspaceSlug = workspaceSlugProp ?? routeWorkspaceSlug ?? null;
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestedIssueId = searchParams.get('issue');

  const reloadAssignedIssues = useCallback(async () => {
    if (!token || !user) {
      return;
    }

    setLoading(true);
    setLoadError(null);
    try {
      const [taskListResponse, issueResponse] = await Promise.all([
        listPmsTaskLists(token, undefined, workspaceSlug),
        listAssignedIssues(token, { limit: 50, workspaceSlug }),
      ]);
      setTaskLists(taskListResponse.items);
      setIssues(issueResponse.items);
      setSelectedIssue((current) => {
        if (!current) {
          return null;
        }
        return issueResponse.items.find((issue) => issue.id === current.id) ?? current;
      });
    } catch (error) {
      setTaskLists([]);
      setIssues([]);
      setLoadError(getErrorMessage(error, t('pms.errors.assignedIssuesLoadFailed')));
    } finally {
      setLoading(false);
    }
  }, [t, token, user, workspaceSlug]);

  useEffect(() => {
    void reloadAssignedIssues();
  }, [reloadAssignedIssues]);

  useEffect(() => {
    if (!token || !requestedIssueId) {
      return;
    }

    const existing = issues.find((issue) => issue.id === requestedIssueId);
    if (existing) {
      setSelectedIssue(existing);
      return;
    }

    let cancelled = false;
    getIssueDetail(token, requestedIssueId)
      .then((detail) => {
        if (!cancelled) {
          setSelectedIssue(detail.issue);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSelectedIssue(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [issues, requestedIssueId, token]);

  const selectedTaskList = useMemo(
    () => (selectedIssue ? taskLists.find((taskList) => taskList.id === selectedIssue.list_id) ?? null : null),
    [taskLists, selectedIssue],
  );

  const handleSelectIssue = useCallback((issue: PmsIssue) => {
    setSelectedIssue(issue);
    const next = new URLSearchParams(searchParams);
    next.set('issue', issue.id);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleClose = useCallback(() => {
    setSelectedIssue(null);
    const next = new URLSearchParams(searchParams);
    next.delete('issue');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-app-bg border-b border-app-border px-8 pt-6 pb-4">
        <h1 className="app-text-title-lg text-app-ink">{t('pms.assignedToMe')}</h1>
        <p className="app-text-body mt-1 text-gray-500">{t('pms.assignedToMeDescription')}</p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {loading ? (
          <div className="flex justify-center py-16">
            <Loader2 size={24} className="animate-spin text-app-accent" />
          </div>
        ) : loadError ? (
          <div className="app-text-body flex justify-center py-16 text-red-400">{loadError}</div>
        ) : (
          <ListView issues={issues} onSelectIssue={handleSelectIssue} />
        )}
      </main>

      <AnimatePresence>
        {selectedIssue && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={handleClose}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            />
            <TaskDetail
              issue={selectedIssue}
              spaceName={selectedTaskList?.team_name}
              canEdit={taskListRoleAllows(selectedTaskList?.role, 'member')}
              onClose={handleClose}
              onUpdate={reloadAssignedIssues}
            />
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
