import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ChevronRight } from 'lucide-react';
import { NAV_ITEMS } from '@/src/constants';

export const AIView = () => {
  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="p-8 max-w-6xl mx-auto space-y-12"
    >
      <header className="space-y-2">
        <h1 className="app-text-title-lg text-app-ink">AI Tools Hub</h1>
        <p className="app-text-body text-gray-400">사내 AI 솔루션을 활용하여 업무 효율을 높이세요.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {NAV_ITEMS.filter(item => item.appId === 'ai').map(item => (
          <Link 
            key={item.id} 
            to={`/tool/${item.id}`}
            className="card hover:border-app-accent transition-all group no-underline"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="p-3 bg-app-surface-sidebar rounded-xl border border-app-border group-hover:bg-app-surface-hover transition-colors">
                <item.icon size={24} className="text-app-accent" />
              </div>
              <ChevronRight size={16} className="text-gray-600 group-hover:text-app-ink transition-colors" />
            </div>
            <h3 className="app-text-title-md mb-2 text-app-ink">{item.title}</h3>
            <p className="app-text-caption leading-relaxed text-gray-500">{item.description}</p>
          </Link>
        ))}
      </div>
    </motion.div>
  );
};
