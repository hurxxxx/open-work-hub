import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Layout,
  FolderKanban,
  Star,
  Lock,
  Search,
  Settings,
  Plus,
  LayoutDashboard,
  List as ListIcon,
  Grid,
  Calendar,
  Activity,
  Table,
  FileText,
  Loader2,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { NAV_ITEMS } from '@/src/constants';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listPmsProjects,
  listProjectIssues,
  listProjectMembers,
  listProjectMilestones,
  listProjectLabels,
  updateIssue,
  type PmsProject,
  type PmsIssue,
  type PmsProjectMember,
  type PmsMilestone,
  type PmsLabel,
} from '@/src/domains/pms/pms-api';

import { OverviewView } from './OverviewView';
import { ListView } from './ListView';
import { BoardView } from './BoardView';
import { CalendarView } from './CalendarView';
import { GanttView } from './GanttView';
import { TableView } from './TableView';
import { TaskDetail } from './TaskDetail';
import { NewTaskModal } from './NewTaskModal';
import { TeamDocsView } from '../TeamDocsView';
import { AssignedToMeView } from './AssignedToMeView';
import { TodayOverdueView } from './TodayOverdueView';
import { PersonalListView } from './PersonalListView';
import { ProjectSettingsPanel } from './ProjectSettingsPanel';

export const PMSView = () => {
  const { toolId } = useParams();
  const { token } = useAuth();
  const [activeTab, setActiveTab] = useState<'Overview' | 'Team Docs' | 'List' | 'Board' | 'Calendar' | 'Gantt' | 'Table'>('List');
  const [selectedIssue, setSelectedIssue] = useState<PmsIssue | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);

  const [projects, setProjects] = useState<PmsProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [members, setMembers] = useState<PmsProjectMember[]>([]);
  const [milestones, setMilestones] = useState<PmsMilestone[]>([]);
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);

  const isAssignedTasksView = toolId === 'pms-tasks' || toolId === 'pms-tasks-assigned';
  const isTodayView = toolId === 'pms-tasks-today';
  const isPersonalView = toolId === 'pms-tasks-personal';
  const isTeamSpace = toolId === 'pms-space-team' || !toolId;
  const currentProject = NAV_ITEMS.find(item => item.id === toolId);
  const projectName = currentProject?.title || 'Team Space';

  // Load projects on mount
  useEffect(() => {
    if (!token) return;
    setLoading(true);
    listPmsProjects(token)
      .then(res => {
        setProjects(res.items);
        if (res.items.length > 0 && !selectedProjectId) {
          setSelectedProjectId(res.items[0].id);
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [token]);

  // Load issues + members + milestones when project changes
  useEffect(() => {
    if (!token || !selectedProjectId) return;
    setLoading(true);
    Promise.all([
      listProjectIssues(token, selectedProjectId, { q: searchQuery }),
      listProjectMembers(token, selectedProjectId),
      listProjectMilestones(token, selectedProjectId),
      listProjectLabels(token, selectedProjectId),
    ])
      .then(([issueRes, memberRes, milestoneRes, labelRes]) => {
        setIssues(issueRes.items);
        setMembers(memberRes.items);
        setMilestones(milestoneRes.items);
        setLabels(labelRes.items);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [token, selectedProjectId, searchQuery]);

  const reloadIssues = useCallback(() => {
    if (!token || !selectedProjectId) return;
    listProjectIssues(token, selectedProjectId, { q: searchQuery })
      .then(res => setIssues(res.items))
      .catch(err => setError(err.message));
  }, [token, selectedProjectId, searchQuery]);

  const handleUpdateIssue = useCallback(
    async (issueId: string, payload: Record<string, unknown>) => {
      if (!token) return;
      await updateIssue(token, issueId, payload);
      reloadIssues();
    },
    [token, reloadIssues],
  );

  useEffect(() => {
    if (isTeamSpace) {
      setActiveTab('Overview');
    } else {
      setActiveTab('List');
    }
  }, [toolId, isTeamSpace]);

  if (isAssignedTasksView) return <AssignedToMeView />;
  if (isTodayView) return <TodayOverdueView />;
  if (isPersonalView) return <PersonalListView />;

  const selectedProject = projects.find(p => p.id === selectedProjectId);

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 transition-colors">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-clickup-purple rounded flex items-center justify-center text-white">
              <Layout size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                {!isTeamSpace && (
                  <>
                    <Link to="/tool/pms-space-team" className="text-xl font-bold text-gray-500 hover:text-clickup-text transition-colors">Team Space</Link>
                    <span className="text-gray-600">/</span>
                  </>
                )}
                <h1 className="text-xl font-bold text-clickup-text flex items-center gap-2">
                  {isTeamSpace && <Layout size={18} className="text-clickup-purple" />}
                  {!isTeamSpace && <FolderKanban size={18} className="text-blue-400" />}
                  {selectedProject?.name || projectName}
                  <Star size={16} className="text-gray-600 cursor-pointer hover:text-yellow-500 ml-2" />
                </h1>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-gray-500">
                <Lock size={10} />
                <span>{isTeamSpace ? 'Private Space' : 'Project Folder'}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {/* Project Selector */}
            {projects.length > 1 && (
              <select
                value={selectedProjectId}
                onChange={e => setSelectedProjectId(e.target.value)}
                className="bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-1.5 text-xs text-clickup-text focus:outline-none focus:border-clickup-purple"
              >
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            )}
            <div className="flex items-center bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-1.5 gap-2">
              <Search size={14} className="text-gray-500" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="bg-transparent text-xs text-clickup-text focus:outline-none w-32"
              />
            </div>
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 hover:bg-clickup-hover rounded border border-clickup-border text-gray-500 dark:text-gray-400"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={() => setIsNewTaskModalOpen(true)}
              className="flex items-center gap-2 px-4 py-2 bg-clickup-purple text-white rounded-md text-sm font-medium shadow-lg shadow-purple-500/20"
            >
              <Plus size={16} />
              <span>New Task</span>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-6">
          {(isTeamSpace ? ['Overview', 'Team Docs', 'List', 'Board', 'Calendar', 'Gantt', 'Table'] : ['List', 'Board', 'Calendar', 'Gantt', 'Table']).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={cn(
                "text-sm font-medium pb-3 transition-all relative",
                activeTab === tab ? "text-clickup-text" : "text-gray-500 hover:text-clickup-text"
              )}
            >
              <div className="flex items-center gap-2">
                {tab === 'Overview' && <LayoutDashboard size={14} />}
                {tab === 'Team Docs' && <FileText size={14} />}
                {tab === 'List' && <ListIcon size={14} />}
                {tab === 'Board' && <Grid size={14} />}
                {tab === 'Calendar' && <Calendar size={14} />}
                {tab === 'Gantt' && <Activity size={14} />}
                {tab === 'Table' && <Table size={14} />}
                {tab}
              </div>
              {activeTab === tab && (
                <motion.div layoutId="activeTab" className="absolute bottom-0 left-0 right-0 h-0.5 bg-clickup-purple" />
              )}
            </button>
          ))}
          <button className="text-gray-500 hover:text-gray-300 pb-3">
            <Plus size={14} />
          </button>
        </div>
      </header>

      <main className={cn(
        "flex-1 custom-scrollbar",
        activeTab === 'Team Docs' ? "overflow-hidden" : "overflow-y-auto p-8"
      )}>
        {loading && issues.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 size={24} className="animate-spin text-clickup-purple" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-64 text-sm text-red-400">{error}</div>
        ) : (
          <AnimatePresence mode="wait">
            {activeTab === 'Overview' && isTeamSpace && (
              <motion.div key="overview" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <OverviewView />
              </motion.div>
            )}
            {activeTab === 'Team Docs' && isTeamSpace && (
              <motion.div key="team-docs" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <TeamDocsView />
              </motion.div>
            )}
            {activeTab === 'List' && (
              <motion.div key="list" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <ListView issues={issues} onSelectIssue={setSelectedIssue} />
              </motion.div>
            )}
            {activeTab === 'Board' && (
              <motion.div key="board" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <BoardView issues={issues} onSelectIssue={setSelectedIssue} onUpdateIssue={handleUpdateIssue} />
              </motion.div>
            )}
            {activeTab === 'Calendar' && (
              <motion.div key="calendar" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <CalendarView issues={issues} />
              </motion.div>
            )}
            {activeTab === 'Gantt' && (
              <motion.div key="gantt" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <GanttView issues={issues} />
              </motion.div>
            )}
            {activeTab === 'Table' && (
              <motion.div key="table" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
                <TableView issues={issues} onSelectIssue={setSelectedIssue} />
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </main>

      {/* Task detail — full-size modal overlay (ClickUp style) */}
      <AnimatePresence>
        {selectedIssue && (
          <motion.div
            key="task-modal"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-stretch"
          >
            <div className="absolute inset-0 bg-black/40" onClick={() => setSelectedIssue(null)} />
            <motion.div
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 30, opacity: 0 }}
              transition={{ type: 'spring', damping: 28, stiffness: 350 }}
              className="relative z-10 my-6 mx-auto w-[80%] bg-clickup-bg border border-clickup-border rounded-xl shadow-2xl overflow-hidden flex flex-col"
            >
              <TaskDetail
                issue={selectedIssue}
                members={members}
                milestones={milestones}
                projectLabels={labels}
                onClose={() => setSelectedIssue(null)}
                onUpdate={reloadIssues}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isNewTaskModalOpen && (
          <NewTaskModal
            isOpen={isNewTaskModalOpen}
            onClose={() => setIsNewTaskModalOpen(false)}
            projectId={selectedProjectId}
            onCreated={reloadIssues}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {settingsOpen && selectedProjectId && (
          <ProjectSettingsPanel
            projectId={selectedProjectId}
            onClose={() => setSettingsOpen(false)}
            onLabelsChanged={(updated) => setLabels(updated)}
          />
        )}
      </AnimatePresence>
    </div>
  );
};
