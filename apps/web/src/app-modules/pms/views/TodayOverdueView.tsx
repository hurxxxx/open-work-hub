import { useState, useEffect } from 'react';
import { Calendar, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { listPmsTaskLists, listTaskListIssues, type PmsIssue } from '@/src/domains/pms/pms-api';
import { initials, formatDate } from './pms-constants';

export const TodayOverdueView = () => {
  const { token } = useAuth();
  const [issues, setIssues] = useState<PmsIssue[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    listPmsTaskLists(token)
      .then(async (res) => {
        const allIssues: PmsIssue[] = [];
        for (const taskList of res.items) {
          const issueRes = await listTaskListIssues(token, taskList.id);
          allIssues.push(...issueRes.items);
        }
        setIssues(allIssues);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const today = new Date().toISOString().slice(0, 10);

  const overdue = issues.filter(
    i => i.due_date && i.due_date < today && i.status !== 'done' && i.status !== 'canceled',
  );
  const todayIssues = issues.filter(
    i => i.due_date === today && i.status !== 'done' && i.status !== 'canceled',
  );

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-app-bg border-b border-app-border px-8 pt-6 pb-4">
        <h1 className="app-text-title-lg text-app-ink">Today & Overdue</h1>
        <p className="app-text-body mt-1 text-gray-500">Focus on what's important right now</p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        {loading ? (
          <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-app-accent" /></div>
        ) : (
          <div className="max-w-4xl mx-auto space-y-8">
            {/* Overdue */}
            <section>
              <div className="flex items-center gap-2 mb-4 text-red-500">
                <AlertCircle size={18} />
                <h2 className="app-text-title-md">Overdue</h2>
                <span className="app-text-label rounded-full bg-red-500/10 px-2 py-0.5 text-red-500">{overdue.length}</span>
              </div>
              <div className="space-y-2">
                {overdue.map(issue => (
                  <IssueAgendaItem key={issue.id} issue={issue} isOverdue />
                ))}
                {overdue.length === 0 && <p className="app-text-body text-app-ink/40">No overdue tasks</p>}
              </div>
            </section>

            {/* Today */}
            <section>
              <div className="flex items-center gap-2 mb-4 text-blue-400">
                <Calendar size={18} />
                <h2 className="app-text-title-md">Today</h2>
                <span className="app-text-label rounded-full bg-blue-400/10 px-2 py-0.5 text-blue-400">{todayIssues.length}</span>
              </div>
              <div className="space-y-2">
                {todayIssues.map(issue => (
                  <IssueAgendaItem key={issue.id} issue={issue} />
                ))}
                {todayIssues.length === 0 && <p className="app-text-body text-app-ink/40">No tasks due today</p>}
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
};

const IssueAgendaItem = ({ issue, isOverdue = false }: { issue: PmsIssue; isOverdue?: boolean }) => (
  <div className="flex items-center justify-between p-4 bg-app-surface-sidebar border border-app-border rounded-lg hover:border-gray-600 transition-colors group cursor-pointer">
    <div className="flex items-center gap-4">
      <button className="text-gray-500 hover:text-green-500 transition-colors">
        <CheckCircle2 size={20} />
      </button>
      <div>
        <div className="flex items-center gap-2">
          <span className="app-text-micro text-app-ink/40">{issue.reference}</span>
          <h3 className="app-text-body font-medium text-app-ink transition-colors group-hover:text-app-accent">{issue.title}</h3>
        </div>
        <div className="app-text-caption mt-1 flex items-center gap-3 text-gray-500">
          <span className={cn("flex items-center gap-1", isOverdue ? "text-red-500" : "")}>
            <Calendar size={12} />
            {formatDate(issue.due_date)}
          </span>
          {issue.labels.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              {issue.labels[0].name}
            </span>
          )}
        </div>
      </div>
    </div>
    {issue.assignee_name && (
      <div className="app-text-micro flex h-6 w-6 items-center justify-center rounded-full bg-app-accent font-medium text-app-accent-fg">
        {initials(issue.assignee_name)}
      </div>
    )}
  </div>
);
