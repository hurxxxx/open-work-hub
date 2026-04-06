import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { 
  LayoutDashboard, 
  Clock, 
  CheckCircle2, 
  Plus, 
  Circle, 
  Activity 
} from 'lucide-react';
import { NAV_ITEMS } from '@/src/constants';

export const HomeView = () => {
  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="p-8 max-w-6xl mx-auto space-y-12"
    >
      <header className="space-y-4">
        <div className="flex items-center gap-3 text-clickup-purple">
          <LayoutDashboard size={32} />
          <h1 className="text-4xl font-bold text-clickup-text tracking-tight">Welcome back, John</h1>
        </div>
        <p className="text-gray-500 dark:text-gray-400 text-lg">오늘의 업무 현황과 AI 도구들을 한눈에 확인하세요.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        <div className="card space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-clickup-text flex items-center gap-2">
              <Clock size={18} className="text-blue-400" />
              최근 사용한 도구
            </h3>
            <button className="text-xs text-clickup-purple hover:underline">전체보기</button>
          </div>
          <div className="space-y-3">
            {NAV_ITEMS.slice(0, 3).map(item => (
              <Link 
                key={item.id} 
                to={`/tool/${item.id}`}
                className="flex items-center gap-3 p-3 bg-clickup-bg rounded-xl border border-clickup-border hover:border-clickup-purple transition-all group"
              >
                <div className="p-2 bg-clickup-sidebar rounded-lg group-hover:bg-clickup-hover transition-colors">
                  <item.icon size={18} className="text-gray-500 group-hover:text-clickup-purple" />
                </div>
                <span className="text-sm text-gray-500 dark:text-gray-300 group-hover:text-clickup-text font-medium">{item.title}</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="card space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-clickup-text flex items-center gap-2">
              <CheckCircle2 size={18} className="text-green-400" />
              오늘의 할 일
            </h3>
            <Plus size={18} className="text-gray-500 cursor-pointer hover:text-clickup-text" />
          </div>
          <div className="space-y-3">
            {[
              { t: '특허 출원 초안 검토', d: '오후 2:00' },
              { t: '주간 업무 보고 작성', d: '오후 5:00' },
              { t: '신규 규격서 비교 분석', d: '내일' },
            ].map((task, i) => (
              <div key={i} className="flex items-center gap-3 p-3 bg-clickup-bg rounded-xl border border-clickup-border group cursor-pointer">
                <Circle size={18} className="text-gray-500 dark:text-gray-600 group-hover:text-clickup-purple" />
                <div className="flex-1">
                  <div className="text-sm text-gray-500 dark:text-gray-300 group-hover:text-clickup-text">{task.t}</div>
                  <div className="text-[10px] text-gray-500 dark:text-gray-600">{task.d}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-clickup-text flex items-center gap-2">
              <Activity size={18} className="text-orange-400" />
              시스템 상태
            </h3>
            <span className="px-2 py-0.5 bg-green-500/20 text-green-500 text-[10px] font-bold rounded uppercase tracking-wider">Stable</span>
          </div>
          <div className="space-y-4">
            <div className="p-4 bg-clickup-bg rounded-xl border border-clickup-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">AI Model Usage</span>
                <span className="text-xs text-clickup-text font-medium">42%</span>
              </div>
              <div className="h-1.5 bg-clickup-sidebar rounded-full overflow-hidden">
                <div className="h-full bg-clickup-purple w-[42%]" />
              </div>
            </div>
            <div className="p-4 bg-clickup-bg rounded-xl border border-clickup-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-500">Storage</span>
                <span className="text-xs text-clickup-text font-medium">12.4 GB / 50 GB</span>
              </div>
              <div className="h-1.5 bg-clickup-sidebar rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 w-[25%]" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};
