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
        <h1 className="text-3xl font-bold text-clickup-text">AI Tools Hub</h1>
        <p className="text-gray-400">사내 AI 솔루션을 활용하여 업무 효율을 높이세요.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {NAV_ITEMS.filter(item => item.appId === 'ai').map(item => (
          <Link 
            key={item.id} 
            to={`/tool/${item.id}`}
            className="card hover:border-clickup-purple transition-all group no-underline"
          >
            <div className="flex items-start justify-between mb-4">
              <div className="p-3 bg-clickup-sidebar rounded-xl border border-clickup-border group-hover:bg-clickup-hover transition-colors">
                <item.icon size={24} className="text-clickup-purple" />
              </div>
              <ChevronRight size={16} className="text-gray-600 group-hover:text-clickup-text transition-colors" />
            </div>
            <h3 className="text-lg font-semibold text-clickup-text mb-2">{item.title}</h3>
            <p className="text-xs text-gray-500 leading-relaxed">{item.description}</p>
          </Link>
        ))}
      </div>
    </motion.div>
  );
};
