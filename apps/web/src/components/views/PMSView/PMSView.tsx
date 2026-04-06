import { useState, useEffect } from 'react';
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
  FileText
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { NAV_ITEMS } from '@/src/constants';
import { Task } from '@/src/types';
import { MOCK_TASKS } from '@/src/mockData';

// Sub-views
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

export const PMSView = () => {
  const { toolId } = useParams();
  const [activeTab, setActiveTab] = useState<'Overview' | 'Team Docs' | 'List' | 'Board' | 'Calendar' | 'Gantt' | 'Table'>('List');
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);
  const isAssignedTasksView = toolId === 'pms-tasks' || toolId === 'pms-tasks-assigned';
  const isTodayView = toolId === 'pms-tasks-today';
  const isPersonalView = toolId === 'pms-tasks-personal';

  const isTeamSpace = toolId === 'pms-space-team' || !toolId;
  const currentProject = NAV_ITEMS.find(item => item.id === toolId);
  const projectName = currentProject?.title || 'Team Space';

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

  const filteredTasks = isTeamSpace 
    ? MOCK_TASKS 
    : MOCK_TASKS.filter(t => t.tags.includes(projectName.replace(' ', '')));

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
                  {projectName}
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
            <div className="flex items-center bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-1.5 gap-2">
              <Search size={14} className="text-gray-500" />
              <input type="text" placeholder="Search..." className="bg-transparent text-xs text-clickup-text focus:outline-none w-32" />
            </div>
            <button className="p-2 hover:bg-clickup-hover rounded border border-clickup-border text-gray-500 dark:text-gray-400">
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
              <ListView tasks={filteredTasks} onSelectTask={setSelectedTask} />
            </motion.div>
          )}
          {activeTab === 'Board' && (
            <motion.div key="board" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
              <BoardView tasks={filteredTasks} onSelectTask={setSelectedTask} />
            </motion.div>
          )}
          {activeTab === 'Calendar' && (
            <motion.div key="calendar" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
              <CalendarView tasks={filteredTasks} />
            </motion.div>
          )}
          {activeTab === 'Gantt' && (
            <motion.div key="gantt" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
              <GanttView tasks={filteredTasks} />
            </motion.div>
          )}
          {activeTab === 'Table' && (
            <motion.div key="table" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="h-full">
              <TableView tasks={filteredTasks} onSelectTask={setSelectedTask} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {selectedTask && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedTask(null)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            />
            <TaskDetail task={selectedTask} onClose={() => setSelectedTask(null)} />
          </>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isNewTaskModalOpen && (
          <NewTaskModal isOpen={isNewTaskModalOpen} onClose={() => setIsNewTaskModalOpen(false)} />
        )}
      </AnimatePresence>
    </div>
  );
};
