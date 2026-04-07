import { useState } from 'react';
import { motion } from 'motion/react';
import { 
  FileText, 
  Link as LinkIcon, 
  Sparkles, 
  Share2, 
  Star,
  Plus,
  MoreHorizontal
} from 'lucide-react';
import { BlockEditor } from '@aidoo/ui';
import { cn } from '@/src/lib/utils';

export const TeamDocsView = () => {
  const [pages, setPages] = useState([
    { id: 'page-1', title: 'Page 1', icon: FileText },
    { id: 'page-21', title: 'Page 21', icon: FileText },
  ]);
  const [activePageId, setActivePageId] = useState('page-1');
  
  const activePage = pages.find(p => p.id === activePageId) || pages[0];

  return (
    <div>
      <div className="h-full flex bg-white dark:bg-[#1e1e24]">
        {/* Local Sidebar for Pages */}
        <div className="w-64 border-r border-clickup-border bg-clickup-sidebar flex flex-col">
          <div className="p-4 flex items-center justify-between">
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Pages</h3>
          </div>
          <div className="flex-1 overflow-y-auto px-2 space-y-1">
            {pages.map(page => (
              <button
                key={page.id}
                onClick={() => setActivePageId(page.id)}
                className={cn(
                  "w-full flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors group",
                  activePageId === page.id 
                    ? "bg-clickup-hover text-clickup-text" 
                    : "text-gray-400 hover:bg-clickup-hover hover:text-gray-300"
                )}
              >
                <div className="flex items-center gap-2">
                  <page.icon size={16} className={activePageId === page.id ? "text-clickup-purple" : "text-gray-500"} />
                  <span className="truncate">{page.title}</span>
                </div>
                <div className={cn(
                  "flex items-center gap-1",
                  activePageId === page.id ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                )}>
                  <Plus size={14} className="text-gray-500 hover:text-gray-300" />
                  <MoreHorizontal size={14} className="text-gray-500 hover:text-gray-300" />
                </div>
              </button>
            ))}
            <button className="w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm text-gray-500 hover:bg-clickup-hover hover:text-gray-300 transition-colors mt-2">
              <Plus size={16} />
              <span>Add page</span>
            </button>
          </div>
        </div>

        {/* Editor Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Editor Header */}
          <div className="h-12 border-b border-clickup-border flex items-center justify-between px-4">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <LinkIcon size={12} />
              <span>Link Task or Doc</span>
            </div>
            <div className="flex items-center gap-4">
              <button className="flex items-center gap-1.5 text-xs text-clickup-purple font-medium">
                <Sparkles size={14} />
                <span>Ask AI</span>
              </button>
              <button className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white">
                <Share2 size={14} />
                <span>Share</span>
              </button>
              <button className="text-gray-400 hover:text-white">
                <Star size={14} />
              </button>
            </div>
          </div>

          {/* Editor Content */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <div className="max-w-4xl mx-auto py-12 px-12 space-y-8">
              <div className="space-y-4">
                <h1 className="text-4xl font-bold text-clickup-text outline-none" contentEditable suppressContentEditableWarning>
                  {activePage.title}
                </h1>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <div className="flex items-center gap-1.5">
                    <div className="w-5 h-5 rounded-full bg-clickup-purple flex items-center justify-center text-[10px] font-bold text-white">GH</div>
                    <span>Gunwoo Hur</span>
                  </div>
                  <span>•</span>
                  <span>Last updated Today at 5:37 pm</span>
                </div>
              </div>

              <div className="prose prose-invert max-w-none">
                <BlockEditor placeholder="Start writing..." />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
