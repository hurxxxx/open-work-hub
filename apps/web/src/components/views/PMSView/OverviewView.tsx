import { Link } from 'react-router-dom';
import {
  Filter,
  History,
  FolderKanban,
  ChevronRight,
  Plus,
  FileText,
  User,
  LayoutDashboard,
} from 'lucide-react';
import { DonutChartCard, BarChartCard, Panel } from '@aidoo/ui';
import { NAV_ITEMS } from '@/src/constants';

export const OverviewView = () => {
  const statusCategories = ['TO DO', 'IN PROGRESS', 'REVIEW', 'DONE'];
  const statusValues = [2, 2, 1, 1];
  const statusColors = ['#6b7280', '#3b82f6', '#f97316', '#22c55e'];

  const projects = NAV_ITEMS.filter(
    (item) => item.appId === 'pms' && item.category === 'Spaces' && item.id !== 'pms-space-team',
  );

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Welcome Section — flat, no gradient */}
      <div className="rounded-xl border border-clickup-border bg-clickup-card p-8">
        <h2 className="text-2xl font-bold text-clickup-text mb-2">Good afternoon, John!</h2>
        <p className="text-clickup-text/60 text-sm max-w-xl">
          Welcome to the Team Space. Here you can find an overview of all projects, documents, and
          shared resources for the entire team.
        </p>
      </div>

      <div className="flex items-center justify-between text-xs text-clickup-text/50 bg-clickup-sidebar/30 p-3 rounded-lg border border-clickup-border">
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
        <Panel>
          <h3 className="text-sm font-bold text-clickup-text flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <History size={16} className="text-clickup-purple" />
              Recent
            </div>
            <button className="text-[10px] text-clickup-text/50 hover:text-clickup-text">
              View all
            </button>
          </h3>
          <div className="space-y-3">
            {projects.map((project) => (
              <Link
                key={project.id}
                to={`/tool/${project.id}`}
                className="flex items-center gap-3 p-2 hover:bg-clickup-hover rounded-md transition-colors group"
              >
                <div className="w-8 h-8 bg-blue-500/10 rounded flex items-center justify-center">
                  <FolderKanban size={16} className="text-blue-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-clickup-text truncate group-hover:text-clickup-purple transition-colors">
                    {project.title}
                  </div>
                  <div className="text-[10px] text-clickup-text/40">Updated 2h ago</div>
                </div>
                <ChevronRight
                  size={14}
                  className="text-clickup-text/30 opacity-0 group-hover:opacity-100 transition-opacity"
                />
              </Link>
            ))}
          </div>
        </Panel>

        {/* Status Distribution — using @aidoo/ui DonutChartCard */}
        <DonutChartCard
          title={
            <span className="flex items-center gap-2 text-sm font-bold text-clickup-text">
              <LayoutDashboard size={16} className="text-clickup-purple" />
              Status Distribution
            </span>
          }
          categories={statusCategories}
          series={statusCategories.map((cat, i) => ({
            key: cat,
            label: cat,
            color: statusColors[i],
            data: [statusValues[i]],
          }))}
        />

        {/* Team Docs */}
        <Panel>
          <h3 className="text-sm font-bold text-clickup-text flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-clickup-purple" />
              Team Docs
            </div>
            <Plus size={16} className="text-clickup-text/50 cursor-pointer hover:text-clickup-text" />
          </h3>
          <div className="space-y-3">
            {[
              { t: 'Product Strategy 2024', d: 'Updated 1h ago', o: 'GH' },
              { t: 'AI Integration Roadmap', d: 'Updated 5h ago', o: 'JD' },
              { t: 'Patent Analysis v1.2', d: 'Updated Yesterday', o: 'AS' },
            ].map((doc, i) => (
              <div
                key={i}
                className="flex items-center gap-3 p-2 hover:bg-clickup-hover rounded-md transition-colors cursor-pointer group"
              >
                <div className="w-8 h-8 bg-clickup-sidebar border border-clickup-border rounded flex items-center justify-center">
                  <FileText
                    size={14}
                    className="text-clickup-text/50 group-hover:text-clickup-purple"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-clickup-text truncate group-hover:text-clickup-purple transition-colors">
                    {doc.t}
                  </div>
                  <div className="text-[10px] text-clickup-text/40">{doc.d}</div>
                </div>
                <div className="w-5 h-5 rounded-full bg-clickup-purple flex items-center justify-center text-[8px] font-bold text-white">
                  {doc.o}
                </div>
              </div>
            ))}
          </div>
          <button className="w-full py-2 text-[10px] font-bold text-clickup-text/50 hover:text-clickup-text border border-dashed border-clickup-border rounded-md transition-colors mt-3">
            View all documents
          </button>
        </Panel>
      </div>

      {/* Workload — using @aidoo/ui BarChartCard */}
      <BarChartCard
        title={
          <span className="flex items-center gap-2 text-sm font-bold text-clickup-text">
            <User size={16} className="text-clickup-purple" />
            Team Workload
          </span>
        }
        categories={['John', 'Jane', 'Mike', 'Sarah', 'Kevin']}
        series={[
          { key: 'tasks', label: 'Tasks', color: '#3b82f6', data: [12, 15, 8, 20, 10] },
          { key: 'completed', label: 'Completed', color: '#22c55e', data: [8, 10, 7, 12, 5] },
        ]}
      />
    </div>
  );
};
