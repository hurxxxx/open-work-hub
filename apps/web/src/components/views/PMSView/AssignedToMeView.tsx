import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { listPmsTaskLists, listTaskListIssues, type PmsIssue, type PmsTaskList } from '@/src/domains/pms/pms-api';
import { taskListRoleAllows } from '@/src/domains/pms/pms-permissions';
import { ListView } from './ListView';
import { TaskDetail } from './TaskDetail';

export const AssignedToMeView = () => {
  const { token, user } = useAuth();
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [taskLists, setTaskLists] = useState<PmsTaskList[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token || !user) return;
    setLoading(true);
    listPmsTaskLists(token)
      .then(async (res) => {
        setTaskLists(res.items);
        const allIssues: PmsIssue[] = [];
        for (const taskList of res.items) {
          const issueRes = await listTaskListIssues(token, taskList.id);
          allIssues.push(...issueRes.items.filter(i => i.assignee_id === user.id));
        }
        setIssues(allIssues);
      })
      .finally(() => setLoading(false));
  }, [token, user]);

  const selectedTaskList = useMemo(
    () => (selectedIssue ? taskLists.find((taskList) => taskList.id === selectedIssue.list_id) ?? null : null),
    [taskLists, selectedIssue],
  );

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-app-bg border-b border-app-border px-8 pt-6 pb-4">
        <h1 className="app-text-title-lg text-app-ink">Assigned to me</h1>
        <p className="app-text-body mt-1 text-gray-500">Tasks assigned to you across all lists</p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-app-accent" /></div>
        ) : (
          <ListView issues={issues} onSelectIssue={setSelectedIssue} />
        )}
      </main>

      <AnimatePresence>
        {selectedIssue && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedIssue(null)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            />
            <TaskDetail
              issue={selectedIssue}
              spaceName={selectedTaskList?.team_name}
              canEdit={taskListRoleAllows(selectedTaskList?.role, 'member')}
              onClose={() => setSelectedIssue(null)}
            />
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
