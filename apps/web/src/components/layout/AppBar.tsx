import { Link } from 'react-router-dom';
import { Settings, Sun, Moon } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { APP_BAR_ITEMS } from '@/src/constants';

export const AppBar = ({ 
  activeAppId, 
  theme, 
  onToggleTheme 
}: { 
  activeAppId: string;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}) => {
  return (
    <div className="w-16 h-full bg-clickup-dark border-r border-clickup-border flex flex-col items-center py-4 gap-4 z-20">
      <div className="w-10 h-10 bg-clickup-purple rounded-lg flex items-center justify-center text-white font-bold mb-4 shadow-lg shadow-clickup-purple/20">
        ID
      </div>
      
      {APP_BAR_ITEMS.map(item => (
        <Link 
          key={item.id} 
          to={item.path}
          className={cn(
            "p-3 rounded-xl transition-all group relative",
            activeAppId === item.id 
              ? "bg-clickup-sidebar text-clickup-purple shadow-inner" 
              : "text-gray-500 hover:text-gray-300 hover:bg-clickup-hover"
          )}
        >
          <item.icon size={22} />
          <div className="absolute left-full ml-2 px-2 py-1 bg-black text-white text-[10px] rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
            {item.title}
          </div>
          {activeAppId === item.id && (
            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-clickup-purple rounded-r-full" />
          )}
        </Link>
      ))}

      <div className="mt-auto flex flex-col gap-4">
        <button 
          onClick={onToggleTheme}
          className="p-3 text-gray-500 hover:text-gray-300 transition-colors"
        >
          {theme === 'dark' ? <Sun size={22} /> : <Moon size={22} />}
        </button>
        <button className="p-3 text-gray-500 hover:text-gray-300 transition-colors">
          <Settings size={22} />
        </button>
        <div className="w-8 h-8 bg-orange-500 rounded-full flex items-center justify-center text-white text-[10px] font-bold cursor-pointer border-2 border-clickup-border">
          JD
        </div>
      </div>
    </div>
  );
};
