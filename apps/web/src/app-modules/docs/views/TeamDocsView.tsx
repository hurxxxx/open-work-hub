import { useState } from 'react';
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
import { useTranslation } from 'react-i18next';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { cn } from '@/src/lib/utils';

export const TeamDocsView = () => {
  const { t } = useTranslation('apps');
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const [pages] = useState(() => [
    { id: 'page-1', title: t('docs.team.pageOne'), icon: FileText },
    { id: 'page-21', title: t('docs.team.pageTwentyOne'), icon: FileText },
  ]);
  const [activePageId, setActivePageId] = useState('page-1');
  
  const activePage = pages.find(p => p.id === activePageId) || pages[0];

  return (
    <div>
      <div className="h-full flex bg-white dark:bg-[#1e1e24]">
        {/* Local Sidebar for Pages */}
        <div className="w-64 border-r border-app-border bg-app-surface-sidebar flex flex-col">
          <div className="p-4 flex items-center justify-between">
            <h3 className="app-text-overline text-gray-500">{t('docs.team.pages')}</h3>
          </div>
          <div className="flex-1 overflow-y-auto px-2 space-y-1">
            {pages.map(page => (
              <button
                key={page.id}
                onClick={() => setActivePageId(page.id)}
                className={cn(
                  "app-text-body group flex w-full items-center justify-between rounded-md px-3 py-2 transition-colors",
                  activePageId === page.id 
                    ? "bg-app-surface-hover text-app-ink" 
                    : "text-gray-400 hover:bg-app-surface-hover hover:text-gray-300"
                )}
              >
                <div className="flex items-center gap-2">
                  <page.icon size={16} className={activePageId === page.id ? "text-app-accent" : "text-gray-500"} />
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
            <button className="app-text-body mt-2 flex w-full items-center gap-2 rounded-md px-3 py-2 text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-gray-300">
              <Plus size={16} />
              <span>{t('docs.addPage')}</span>
            </button>
          </div>
        </div>

        {/* Editor Area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Editor Header */}
          <div className="h-12 border-b border-app-border flex items-center justify-between px-4">
            <div className="app-text-caption flex items-center gap-2 text-gray-500">
              <LinkIcon size={12} />
              <span>{t('docs.team.linkTaskOrDoc')}</span>
            </div>
            <div className="flex items-center gap-4">
              <button className="app-text-control-sm flex items-center gap-1.5 text-app-accent">
                <Sparkles size={14} />
                <span>{t('docs.askAi')}</span>
              </button>
              <button className="app-text-control-sm flex items-center gap-1.5 text-gray-400 hover:text-white">
                <Share2 size={14} />
                <span>{t('common:actions.share')}</span>
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
                <h1 className="app-text-title-xl text-app-ink outline-none" contentEditable suppressContentEditableWarning>
                  {activePage.title}
                </h1>
                <div className="app-text-caption flex items-center gap-3 text-gray-500">
                  <div className="flex items-center gap-1.5">
                    <div className="app-text-micro flex h-5 w-5 items-center justify-center rounded-full bg-app-accent font-bold text-app-bg">GH</div>
                    <span>{t('docs.team.sampleAuthor')}</span>
                  </div>
                  <span>•</span>
                  <span>{t('docs.team.lastUpdated', { time: t('docs.team.sampleUpdatedTime') })}</span>
                </div>
              </div>

              <div className="prose dark:prose-invert max-w-none">
                <BlockEditor
                  placeholder={t('docs.startWriting')}
                  uploadFile={uploadFile}
                  resolveFileUrl={resolveFileUrl}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
