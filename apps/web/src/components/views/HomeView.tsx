import { Link } from 'react-router-dom';
import {
  Search,
  Circle,
  Star,
  ChevronRight,
  Flag,
} from 'lucide-react';
import { NAV_ITEMS } from '@/src/constants';
import { useAuth } from '@/src/domains/auth/auth-provider';

function SectionHeader({
  title,
  actionLabel,
  actionTo,
}: {
  title: string;
  actionLabel?: string;
  actionTo?: string;
}) {
  return (
    <div className="flex items-center justify-between mb-1">
      <h2 className="app-text-title-md text-clickup-text">{title}</h2>
      {actionLabel && actionTo ? (
        <Link
          to={actionTo}
          className="app-text-caption text-gray-500 transition-colors hover:text-clickup-text"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}

const assignedTasks = [
  { id: '1', name: '특허 출원 초안 검토', due: '오후 2:00', priority: 'high' as const },
  { id: '2', name: '주간 업무 보고 작성', due: '오후 5:00', priority: 'medium' as const },
  { id: '3', name: '신규 규격서 비교 분석', due: '내일', priority: 'low' as const },
];

const priorityColor: Record<string, string> = {
  high: 'text-red-500',
  medium: 'text-orange-400',
  low: 'text-gray-400',
};

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export const HomeView = () => {
  const auth = useAuth();
  const userName = auth.user?.display_name || auth.user?.full_name || 'User';
  const recentTools = NAV_ITEMS.slice(0, 5);

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="max-w-3xl mx-auto px-8 py-10 space-y-10">
        {/* Header */}
        <div>
          <h1 className="app-text-title-lg text-clickup-text">
            {getGreeting()}, {userName}
          </h1>
          <p className="app-text-body mt-1 text-gray-500">오늘의 업무와 최근 작업을 확인하세요.</p>
        </div>

        {/* Search */}
        <div className="relative">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search everything..."
            className="app-text-body w-full rounded-md border border-clickup-border bg-clickup-bg py-2.5 pl-10 pr-4 text-clickup-text placeholder:text-gray-400 transition-colors focus:border-clickup-purple focus:outline-none"
          />
          <kbd className="app-text-micro absolute right-3.5 top-1/2 -translate-y-1/2 hidden items-center gap-0.5 rounded border border-clickup-border bg-clickup-sidebar px-1.5 py-0.5 text-gray-500 sm:inline-flex">
            ⌘K
          </kbd>
        </div>

        {/* Assigned to me */}
        <section>
          <SectionHeader title="Assigned to me" actionLabel="See all" actionTo="/pms" />
          <div className="border-t border-clickup-border">
            {assignedTasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center gap-3 py-3 border-b border-clickup-border last:border-b-0 group cursor-pointer hover:bg-clickup-hover/50 -mx-2 px-2 rounded-sm transition-colors"
              >
                <Circle size={16} className="text-gray-400 group-hover:text-clickup-purple shrink-0 transition-colors" />
                <span className="app-text-body flex-1 truncate text-clickup-text">{task.name}</span>
                <span className="app-text-caption shrink-0 text-gray-500">{task.due}</span>
                <Flag size={13} className={`${priorityColor[task.priority]} shrink-0`} />
              </div>
            ))}
            {assignedTasks.length === 0 && (
              <p className="app-text-body py-6 text-center text-gray-500">할당된 작업이 없습니다.</p>
            )}
          </div>
        </section>

        {/* Recently visited */}
        <section>
          <SectionHeader title="Recently visited" actionLabel="See all" actionTo="/ai" />
          <div className="border-t border-clickup-border">
            {recentTools.map((item) => (
              <Link
                key={item.id}
                to={`/tool/${item.id}`}
                className="flex items-center gap-3 py-3 border-b border-clickup-border last:border-b-0 group -mx-2 px-2 rounded-sm hover:bg-clickup-hover/50 transition-colors"
              >
                <div className="w-7 h-7 rounded-md bg-clickup-sidebar border border-clickup-border flex items-center justify-center shrink-0 group-hover:border-clickup-purple/40 transition-colors">
                  <item.icon size={14} className="text-gray-500 group-hover:text-clickup-purple transition-colors" />
                </div>
                <div className="flex-1 min-w-0">
                  <span className="app-text-body block truncate text-clickup-text">{item.title}</span>
                  {item.description ? (
                    <span className="app-text-caption block truncate text-gray-500">{item.description}</span>
                  ) : null}
                </div>
                <ChevronRight size={14} className="text-gray-400 opacity-0 group-hover:opacity-100 shrink-0 transition-opacity" />
              </Link>
            ))}
          </div>
        </section>

        {/* Favorites */}
        <section>
          <SectionHeader title="Favorites" />
          <div className="border-t border-clickup-border py-8 text-center">
            <Star size={20} className="mx-auto text-gray-400 mb-2" />
            <p className="app-text-body text-gray-500">즐겨찾기한 도구나 문서가 없습니다.</p>
            <p className="app-text-caption mt-1 text-gray-400">자주 쓰는 항목에 ★ 표시하면 여기에 나타납니다.</p>
          </div>
        </section>
      </div>
    </div>
  );
};
