import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronDown, ChevronRight, Plus, FileText } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { NAV_ITEMS, APP_BAR_ITEMS } from '@/src/constants';

export const SubSidebar = ({ activeAppId, activeNavItemId }: { activeAppId: string, activeNavItemId: string }) => {
  const location = useLocation();
  const isDocEditor = location.pathname.match(/^\/tool\/[^\/]+\/[^\/]+$/) || location.pathname.match(/^\/docs\/[^\/]+$/);
  
  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  
  const filteredItems = NAV_ITEMS.filter(item => item.appId === activeAppId);
  const categories = Array.from(new Set(filteredItems.map(item => item.category)));

  useEffect(() => {
    setExpandedCategories(categories);
  }, [activeAppId]);

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev => 
      prev.includes(category) 
        ? prev.filter(c => c !== category) 
        : [...prev, category]
    );
  };

  if (activeAppId === 'home' || isDocEditor) return null;

  return (
    <div className="w-60 h-full bg-clickup-sidebar border-r border-clickup-border flex flex-col overflow-hidden">
      <div className="p-4 border-b border-clickup-border">
        <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">
          {APP_BAR_ITEMS.find(a => a.id === activeAppId)?.title}
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto py-4 px-2 space-y-6 custom-scrollbar">
        {categories.map(category => (
          <div key={category} className="space-y-1">
            <button 
              onClick={() => toggleCategory(category)}
              className="w-full flex items-center justify-between px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-gray-500 hover:text-gray-300 transition-colors"
            >
              <span>{category}</span>
              {expandedCategories.includes(category) ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            
            <AnimatePresence initial={false}>
              {expandedCategories.includes(category) && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  {filteredItems.filter(item => item.category === category).map(item => {
                    // Special handling for PMS Spaces hierarchy
                    if (activeAppId === 'pms' && category === 'Spaces') {
                      if (item.id === 'pms-space-team') {
                        const subProjects = filteredItems.filter(i => i.category === 'Spaces' && i.id !== 'pms-space-team');
                        return (
                          <div key={item.id} className="space-y-1">
                            <Link 
                              to={`/tool/${item.id}`}
                              className={cn("sidebar-item ml-1", activeNavItemId === item.id && "active")}
                            >
                              <item.icon size={16} className="text-gray-400" />
                              <span className="truncate">{item.title}</span>
                            </Link>
                            <div className="ml-6 border-l border-clickup-border pl-2 space-y-1">
                              {subProjects.map(sub => (
                                <Link 
                                  key={sub.id} 
                                  to={`/tool/${sub.id}`}
                                  className={cn("sidebar-item text-[11px] py-1", activeNavItemId === sub.id && "active")}
                                >
                                  <sub.icon size={14} className="text-gray-500" />
                                  <span className="truncate">{sub.title}</span>
                                </Link>
                              ))}
                            </div>
                          </div>
                        );
                      }
                      // Skip other projects as they are rendered as children of team space
                      return null;
                    }

                    // Special handling for PMS Personal hierarchy (My Tasks)
                    if (activeAppId === 'pms' && category === 'Personal') {
                      if (item.id === 'pms-tasks') {
                        const subTasks = filteredItems.filter(i => i.category === 'Personal' && i.id.startsWith('pms-tasks-'));
                        const isMyTasksActive = activeNavItemId === 'pms-tasks' || activeNavItemId.startsWith('pms-tasks-');
                        
                        return (
                          <div key={item.id} className="space-y-1">
                            <div 
                              className={cn("sidebar-item ml-1 cursor-default", isMyTasksActive && "text-clickup-text")}
                            >
                              <item.icon size={16} className={cn("text-gray-400", isMyTasksActive && "text-clickup-purple")} />
                              <span className="truncate font-semibold">{item.title}</span>
                            </div>
                            <div className="ml-6 border-l border-clickup-border pl-2 space-y-1">
                              {subTasks.map(sub => (
                                <Link 
                                  key={sub.id} 
                                  to={`/tool/${sub.id}`}
                                  className={cn("sidebar-item text-[11px] py-1", activeNavItemId === sub.id && "active")}
                                >
                                  <sub.icon size={14} className="text-gray-500" />
                                  <span className="truncate">{sub.title}</span>
                                </Link>
                              ))}
                            </div>
                          </div>
                        );
                      }
                      // Skip sub-tasks as they are rendered as children of My Tasks
                      if (item.id.startsWith('pms-tasks-')) {
                        return null;
                      }
                    }

                    return (
                      <Link 
                        key={item.id} 
                        to={`/tool/${item.id}`}
                        className={cn("sidebar-item ml-1", activeNavItemId === item.id && "active")}
                      >
                        <item.icon size={16} className="text-gray-400" />
                        <span className="truncate">{item.title}</span>
                      </Link>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ))}
      </div>

      <div className="p-4 border-t border-clickup-border">
        <button className="w-full flex items-center gap-2 px-3 py-2 bg-clickup-purple hover:bg-opacity-90 text-white rounded-md text-sm font-medium transition-all">
          <Plus size={18} />
          <span>Quick Add</span>
        </button>
      </div>
    </div>
  );
};
