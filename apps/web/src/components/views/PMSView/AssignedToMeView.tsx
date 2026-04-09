import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Loader2 } from 'lucide-react';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { listPmsProjects, listProjectIssues, type PmsIssue, type PmsList } from '@/src/domains/pms/pms-api';
import { projectRoleAllows } from '@/src/domains/pms/pms-permissions';
import { ListView } from './ListView';
import { TaskDetail } from './TaskDetail';

export const AssignedToMeView = () => {
  const { token, user } = useAuth();
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [projects, setProjects] = useState<PmsList[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token || !user) return;
    setLoading(true);
    listPmsProjects(token)
      .then(async (res) => {
        setProjects(res.items);
        const allIssues: PmsIssue[] = [];
        for (const project of res.items) {
          const issueRes = await listProjectIssues(token, project.id);
          allIssues.push(...issueRes.items.filter(i => i.assignee_id === user.id));
        }
        setIssues(allIssues);
      })
      .finally(() => setLoading(false));
  }, [token, user]);

  const selectedProject = useMemo(
    () => (selectedIssue ? projects.find((project) => project.id === selectedIssue.project_id) ?? null : null),
    [projects, selectedIssue],
  );

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 pb-4">
        <h1 className="app-text-title-lg text-clickup-text">Assigned to me</h1>
        <p className="app-text-body mt-1 text-gray-500">Tasks assigned to you across all projects</p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-clickup-purple" /></div>
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
              spaceName={selectedProject?.team_name}
              canEdit={projectRoleAllows(selectedProject?.role, 'member')}
              onClose={() => setSelectedIssue(null)}
            />
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
