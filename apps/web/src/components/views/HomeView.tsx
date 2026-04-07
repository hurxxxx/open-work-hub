import { Link } from 'react-router-dom';
import {
  Search,
  Clock,
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
      <h2 className="text-sm font-semibold text-clickup-text">{title}</h2>
      {actionLabel && actionTo ? (
        <Link
          to={actionTo}
          className="text-xs text-gray-500 hover:text-clickup-text transition-colors"
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
          <h1 className="text-2xl font-semibold text-clickup-text tracking-tight">
            {getGreeting()}, {userName}
          </h1>
          <p className="text-sm text-gray-500 mt-1">오늘의 업무와 최근 작업을 확인하세요.</p>
        </div>

        {/* Search */}
        <div className="relative">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search everything..."
            className="w-full rounded-md border border-clickup-border bg-clickup-bg pl-10 pr-4 py-2.5 text-sm text-clickup-text placeholder:text-gray-400 focus:border-clickup-purple focus:outline-none transition-colors"
          />
          <kbd className="absolute right-3.5 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-0.5 rounded border border-clickup-border bg-clickup-sidebar px-1.5 py-0.5 text-[10px] text-gray-500">
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
                <span className="flex-1 text-sm text-clickup-text truncate">{task.name}</span>
                <span className="text-xs text-gray-500 shrink-0">{task.due}</span>
                <Flag size={13} className={`${priorityColor[task.priority]} shrink-0`} />
              </div>
            ))}
            {assignedTasks.length === 0 && (
              <p className="py-6 text-sm text-gray-500 text-center">할당된 작업이 없습니다.</p>
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
                  <span className="text-sm text-clickup-text truncate block">{item.title}</span>
                  {item.description ? (
                    <span className="text-xs text-gray-500 truncate block">{item.description}</span>
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
            <p className="text-sm text-gray-500">즐겨찾기한 도구나 문서가 없습니다.</p>
            <p className="text-xs text-gray-400 mt-1">자주 쓰는 항목에 ★ 표시하면 여기에 나타납니다.</p>
          </div>
        </section>
      </div>
    </div>
  );
};
