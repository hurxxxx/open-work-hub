import { motion } from 'motion/react';
import { 
  Share2, 
  History, 
  FilePlus, 
  Mic, 
  Brain, 
  Activity, 
  FileText, 
  HelpCircle 
} from 'lucide-react';
import type { NavItem } from '@/src/app/shell/navigation-types';

export const ToolView = ({ item }: { item: NavItem }) => {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-8 max-w-5xl mx-auto"
    >
      <div className="card space-y-8">
        <header className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="p-4 bg-app-bg rounded-2xl border border-app-border">
              <item.icon size={32} className="text-app-accent" />
            </div>
            <div>
              <h1 className="app-text-title-lg mb-2 text-app-ink">{item.title}</h1>
              <p className="app-text-body text-gray-500 dark:text-gray-400">{item.description}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="p-2 hover:bg-app-surface-hover rounded-md border border-app-border text-gray-500 dark:text-gray-400">
              <Share2 size={18} />
            </button>
            <button className="p-2 hover:bg-app-surface-hover rounded-md border border-app-border text-gray-500 dark:text-gray-400">
              <History size={18} />
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 space-y-6">
            <div className="space-y-4">
              <label className="app-text-control text-gray-500 dark:text-gray-400">Input Content</label>
              <textarea 
                className="app-text-body h-64 w-full resize-none rounded-xl border border-app-border bg-app-bg p-6 leading-relaxed text-app-ink transition-all focus:border-app-accent focus:outline-none"
                placeholder="여기에 내용을 입력하거나 파일을 업로드하세요..."
              />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex gap-2">
                <button className="app-text-control flex items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink transition-all hover:bg-app-surface-hover">
                  <FilePlus size={18} />
                  <span>파일 업로드</span>
                </button>
                <button className="app-text-control flex items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-4 py-2 text-app-ink transition-all hover:bg-app-surface-hover">
                  <Mic size={18} />
                  <span>음성 입력</span>
                </button>
              </div>
              <button className="app-text-control flex items-center gap-2 rounded-lg bg-app-accent px-8 py-2.5 font-semibold text-app-accent-fg shadow-sm transition-all hover:bg-opacity-90">
                <Brain size={18} />
                <span>AI 실행하기</span>
              </button>
            </div>
          </div>

          <div className="space-y-6">
            <div className="card bg-app-bg/50 border-dashed">
              <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-app-ink">
                <Activity size={16} className="text-app-accent" />
                최근 작업 내역
              </h3>
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md transition-colors cursor-pointer group">
                    <div className="w-8 h-8 rounded bg-app-surface-sidebar border border-app-border flex items-center justify-center">
                      <FileText size={14} className="text-gray-500 group-hover:text-app-accent" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="app-text-caption truncate text-app-ink">작업 문서 #{i}</div>
                      <div className="app-text-micro text-gray-500">2시간 전</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card bg-app-bg/50 border-dashed">
              <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-app-ink">
                <HelpCircle size={16} className="text-app-accent" />
                도움말
              </h3>
              <p className="app-text-caption leading-relaxed text-gray-500">
                이 도구는 사내 문서를 기반으로 최적의 결과물을 생성합니다. 
                더 정확한 결과를 위해 상세한 컨텍스트를 제공해 주세요.
              </p>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};
