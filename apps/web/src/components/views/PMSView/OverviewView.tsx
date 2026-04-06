import { Link } from 'react-router-dom';
import { 
  Sparkles, 
  Filter, 
  History, 
  FolderKanban, 
  ChevronRight, 
  Plus, 
  FileText, 
  User, 
  LayoutDashboard 
} from 'lucide-react';
import { 
  PieChart, 
  Pie, 
  Cell, 
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip
} from 'recharts';
import { NAV_ITEMS } from '@/src/constants';

export const OverviewView = () => {
  const statusData = [
    { name: 'TO DO', value: 2, color: '#6b7280' },
    { name: 'IN PROGRESS', value: 2, color: '#3b82f6' },
    { name: 'REVIEW', value: 1, color: '#f97316' },
    { name: 'DONE', value: 1, color: '#22c55e' },
  ];

  const projects = NAV_ITEMS.filter(item => item.appId === 'pms' && item.category === 'Spaces' && item.id !== 'pms-space-team');

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Welcome Section */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-clickup-purple/20 to-blue-500/20 border border-clickup-purple/30 p-8">
        <div className="relative z-10">
          <h2 className="text-2xl font-bold text-clickup-text mb-2">Good afternoon, John! 👋</h2>
          <p className="text-gray-400 text-sm max-w-xl">
            Welcome to the Team Space. Here you can find an overview of all projects, documents, and shared resources for the entire team.
          </p>
        </div>
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-clickup-purple/10 to-transparent pointer-events-none" />
        <Sparkles className="absolute right-8 top-8 text-clickup-purple opacity-20" size={64} />
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500 bg-clickup-sidebar/30 p-3 rounded-lg border border-clickup-border">
        <div className="flex items-center gap-2">
          <Filter size={14} />
          <span>Filters</span>
        </div>
        <div className="flex items-center gap-4">
          <span>Refreshed: just now</span>
          <div className="flex items-center gap-2">
            <div className="w-8 h-4 bg-clickup-purple rounded-full relative">
              <div className="absolute right-1 top-1 w-2 h-2 bg-white rounded-full" />
            </div>
            <span>Auto refresh: On</span>
          </div>
          <button className="text-clickup-purple font-bold">Add card</button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Recent */}
        <div className="card space-y-4">
          <h3 className="text-sm font-bold text-clickup-text flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History size={16} className="text-clickup-purple" />
              Recent
            </div>
            <button className="text-[10px] text-gray-500 hover:text-clickup-text">View all</button>
          </h3>
          <div className="space-y-3">
            {projects.map(project => (
              <Link key={project.id} to={`/tool/${project.id}`} className="flex items-center gap-3 p-2 hover:bg-clickup-hover rounded-md transition-colors group">
                <div className="w-8 h-8 bg-blue-500/10 rounded flex items-center justify-center">
                  <FolderKanban size={16} className="text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-clickup-text truncate group-hover:text-clickup-purple transition-colors">{project.title}</div>
                  <div className="text-[10px] text-gray-600">Updated 2h ago</div>
                </div>
                <ChevronRight size={14} className="text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity" />
              </Link>
            ))}
          </div>
        </div>

        {/* Status Distribution */}
        <div className="card space-y-4">
          <h3 className="text-sm font-bold text-clickup-text flex items-center gap-2">
            <LayoutDashboard size={16} className="text-clickup-purple" />
            Status Distribution
          </h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={60}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {statusData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip 
                  contentStyle={{ backgroundColor: '#1e1e24', border: '1px solid #33333d', borderRadius: '8px' }}
                  itemStyle={{ fontSize: '10px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {statusData.map(status => (
              <div key={status.name} className="flex items-center gap-2 px-2 py-1 bg-clickup-sidebar/50 rounded border border-clickup-border">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: status.color }} />
                <span className="text-[10px] text-gray-500 truncate">{status.name}</span>
                <span className="text-[10px] font-bold text-clickup-text ml-auto">{status.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Team Docs */}
        <div className="card space-y-4">
          <h3 className="text-sm font-bold text-clickup-text flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-clickup-purple" />
              Team Docs
            </div>
            <Plus size={16} className="text-gray-500 cursor-pointer hover:text-clickup-text" />
          </h3>
          <div className="space-y-3">
            {[
              { t: 'Product Strategy 2024', d: 'Updated 1h ago', o: 'GH' },
              { t: 'AI Integration Roadmap', d: 'Updated 5h ago', o: 'JD' },
              { t: 'Patent Analysis v1.2', d: 'Updated Yesterday', o: 'AS' },
            ].map((doc, i) => (
              <div key={i} className="flex items-center gap-3 p-2 hover:bg-clickup-hover rounded-md transition-colors cursor-pointer group">
                <div className="w-8 h-8 bg-clickup-sidebar border border-clickup-border rounded flex items-center justify-center">
                  <FileText size={14} className="text-gray-500 group-hover:text-clickup-purple" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-clickup-text truncate group-hover:text-clickup-purple transition-colors">{doc.t}</div>
                  <div className="text-[10px] text-gray-600">{doc.d}</div>
                </div>
                <div className="w-5 h-5 rounded-full bg-clickup-purple flex items-center justify-center text-[8px] font-bold text-white">
                  {doc.o}
                </div>
              </div>
            ))}
          </div>
          <button className="w-full py-2 text-[10px] font-bold text-gray-500 hover:text-clickup-text border border-dashed border-clickup-border rounded-md transition-colors">
            View all documents
          </button>
        </div>
      </div>

      {/* Workload */}
      <div className="card space-y-6">
        <h3 className="text-sm font-bold text-clickup-text flex items-center gap-2">
          <User size={16} className="text-clickup-purple" />
          Team Workload
        </h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={[
              { name: 'John', tasks: 12, completed: 8 },
              { name: 'Jane', tasks: 15, completed: 10 },
              { name: 'Mike', tasks: 8, completed: 7 },
              { name: 'Sarah', tasks: 20, completed: 12 },
              { name: 'Kevin', tasks: 10, completed: 5 },
            ]}>
              <XAxis dataKey="name" stroke="#6b7280" fontSize={10} />
              <YAxis stroke="#6b7280" fontSize={10} />
              <RechartsTooltip 
                contentStyle={{ backgroundColor: '#1e1e24', border: '1px solid #33333d', borderRadius: '8px' }}
                itemStyle={{ fontSize: '10px' }}
              />
              <Bar dataKey="tasks" fill="#3b82f6" radius={[4, 4, 0, 0]} />
              <Bar dataKey="completed" fill="#22c55e" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};
