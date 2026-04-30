import { motion } from 'motion/react';
import { Construction } from 'lucide-react';

import type { NavItem } from '@/src/app/shell/navigation-types';

export const ComingSoonView = ({ item }: { item: NavItem }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto max-w-3xl p-8"
    >
      <div className="card space-y-6">
        <header className="flex items-start gap-4">
          <div className="rounded-2xl border border-app-border bg-app-bg p-4">
            <item.icon size={32} className="text-app-accent" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="app-text-title-lg text-app-ink">{item.title}</h1>
              <span className="rounded border border-app-border bg-app-bg px-2 py-0.5 text-[11px] uppercase tracking-wide text-gray-500">
                준비중
              </span>
            </div>
            {item.description ? (
              <p className="mt-2 app-text-body text-gray-500 dark:text-gray-400">
                {item.description}
              </p>
            ) : null}
          </div>
        </header>

        <div className="rounded-xl border border-dashed border-app-border bg-app-bg/40 p-6">
          <div className="flex items-start gap-3">
            <Construction size={20} className="mt-0.5 shrink-0 text-app-accent" />
            <div className="space-y-2">
              <p className="app-text-body text-app-ink">
                이 도구는 기존 사내 AI 포털(legacy_ai_portal_prototype)의 기능을 새 플랫폼으로 포팅하는 작업을 진행 중입니다.
              </p>
              <p className="app-text-caption text-gray-500 dark:text-gray-400">
                준비가 끝나면 이 화면이 실제 도구로 교체됩니다. 먼저 사용해야 하는 작업이 있으면 관리자에게 알려주세요.
              </p>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};
