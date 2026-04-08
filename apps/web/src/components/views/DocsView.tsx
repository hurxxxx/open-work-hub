import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Files, 
  User, 
  Share2, 
  Lock, 
  Mic, 
  History, 
  FileText, 
  Sparkles, 
  Star, 
  X, 
  Plus, 
  Filter, 
  Activity, 
  FileSearch,
  Search,
  MoreHorizontal,
  Settings,
  Trash2,
  Link as LinkIcon
} from 'lucide-react';
import { BlockEditor } from '@aidoo/ui';
import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import { cn } from '@/src/lib/utils';

interface Page {
  id: string;
  title: string;
  content: unknown;
  parentId?: string;
}

interface DocCollection {
  id: string;
  title: string;
  owner: string;
  date: string;
  category: string;
  favorite: boolean;
  pages: Page[];
}

const MOCK_DOCS: DocCollection[] = [
  { 
    id: 'doc-1', 
    title: 'Project Roadmap 2024', 
    owner: 'John Doe', 
    date: 'May 12', 
    category: 'docs-my', 
    favorite: true,
    pages: [
      { id: 'p1', title: 'Q1 Goals', content: null },
      { id: 'p2', title: 'Q2 Strategy', content: null },
      { id: 'p3', title: 'Resource Planning', content: null },
    ]
  },
  { 
    id: 'doc-2', 
    title: 'Technical Specification v1.2', 
    owner: 'Jane Smith', 
    date: 'May 10', 
    category: 'docs-shared', 
    favorite: false,
    pages: [
      { id: 'p4', title: 'Architecture Overview', content: null },
      { id: 'p5', title: 'API Endpoints', content: null },
      { id: 'p6', title: 'Database Schema', content: null },
    ]
  },
  { 
    id: 'doc-3', 
    title: 'Meeting Notes: AI Integration', 
    owner: 'John Doe', 
    date: 'May 08', 
    category: 'docs-notes', 
    favorite: false,
    pages: [
      { id: 'p7', title: 'Initial Brainstorming', content: null },
      { id: 'p8', title: 'Action Items', content: null },
    ]
  },
  { 
    id: 'doc-4', 
    title: 'Patent Analysis Report', 
    owner: 'AI Assistant', 
    date: 'May 05', 
    category: 'docs-private', 
    favorite: false,
    pages: [
      { id: 'p9', title: 'Executive Summary', content: null },
      { id: 'p10', title: 'Competitor Analysis', content: null },
    ]
  },
  { 
    id: 'pms-team-docs-1', 
    title: 'Team Docs: Strategy', 
    owner: 'Gunwoo Hur', 
    date: 'Today', 
    category: 'docs-all', 
    favorite: true,
    pages: [
      { id: 'p11', title: 'Mission Statement', content: null },
      { id: 'p12', title: 'Core Values', content: null },
      { id: 'p13', title: '2024 Vision', content: null },
    ]
  },
];

export const DocsView = () => {
  const { toolId, docId } = useParams();
  const navigate = useNavigate();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const categories = [
    { id: 'docs-all', title: 'All Docs', icon: Files },
    { id: 'docs-my', title: 'My Docs', icon: User },
    { id: 'docs-shared', title: 'Shared with me', icon: Share2 },
    { id: 'docs-private', title: 'Private', icon: Lock },
    { id: 'docs-notes', title: 'Meeting Notes', icon: Mic },
    { id: 'docs-recent', title: 'Recent Pages', icon: History },
    { id: 'docs-archived', title: 'Archived', icon: History },
  ];

  const activeCategory = categories.find(c => c.id === toolId)?.title || 'All Docs';

  const filteredDocs = MOCK_DOCS.filter(doc => {
    const matchesCategory = activeCategory === 'All Docs' || doc.category === toolId;
    const matchesSearch = doc.title.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const selectedDoc = MOCK_DOCS.find(d => d.id === docId);
  const activePage = selectedDoc?.pages.find(p => p.id === selectedPageId) || selectedDoc?.pages[0];

  const handleDocClick = (id: string) => {
    if (toolId) {
      navigate(`/tool/${toolId}/${id}`);
    } else {
      navigate(`/docs/${id}`);
    }
    const doc = MOCK_DOCS.find(d => d.id === id);
    if (doc && doc.pages.length > 0) {
      setSelectedPageId(doc.pages[0].id);
    }
  };

  const handleBack = () => {
    if (toolId) {
      navigate(`/tool/${toolId}`);
    } else {
      navigate(`/docs`);
    }
  };

  // Document Editor View
  const renderEditor = () => {
    if (!selectedDoc) return (
      <div className="flex-1 flex items-center justify-center text-gray-500 bg-clickup-bg">
        <div className="text-center">
          <FileSearch size={48} className="mx-auto mb-4 opacity-20" />
          <h2 className="app-text-title-md text-clickup-text">Document not found</h2>
          <p className="app-text-body text-gray-500">ID: {docId}</p>
          <button onClick={handleBack} className="app-text-control mt-4 text-clickup-purple hover:underline">Go back</button>
        </div>
      </div>
    );
    
    return (
      <div className="h-full flex flex-col bg-clickup-bg overflow-hidden">
          {/* Top Header (Breadcrumbs + Search + Actions) */}
          <div className="h-12 border-b border-clickup-border flex items-center justify-between px-4 bg-clickup-sidebar">
            <div className="app-text-caption flex items-center gap-2">
              <span className="cursor-pointer text-gray-500 hover:text-gray-300" onClick={handleBack}>Docs</span>
              <span className="text-gray-600">/</span>
              <div className="flex items-center gap-2 px-2 py-1 hover:bg-clickup-hover rounded cursor-pointer">
                <FileText size={14} className="text-clickup-purple" />
                <span className="app-text-control text-clickup-text">{selectedDoc.title}</span>
                <Star size={12} className={cn("text-gray-600", selectedDoc.favorite && "text-yellow-500 fill-yellow-500")} />
              </div>
            </div>

            <div className="flex-1 max-w-md mx-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
                <input 
                  type="text" 
                  placeholder="Search K"
                  className="app-text-body-sm w-full rounded-md border border-clickup-border bg-clickup-bg py-1.5 pl-9 pr-4 text-clickup-text focus:border-clickup-purple focus:outline-none"
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button className="p-1.5 hover:bg-clickup-hover rounded text-gray-500">
                <Settings size={16} />
              </button>
              <button className="app-text-control-sm flex items-center gap-1.5 rounded-md px-3 py-1.5 text-clickup-purple transition-colors hover:bg-clickup-purple/10">
                <Sparkles size={14} />
                <span>Ask AI</span>
              </button>
              <button className="app-text-control-sm flex items-center gap-1.5 rounded px-2 py-1.5 text-gray-400 hover:bg-clickup-hover hover:text-white">
                <Share2 size={14} />
                <span>Share</span>
              </button>
              <button className="p-1.5 hover:bg-clickup-hover rounded text-gray-500">
                <MoreHorizontal size={18} />
              </button>
              <div className="app-text-micro flex h-6 w-6 items-center justify-center rounded-full bg-clickup-purple font-bold text-white">
                {selectedDoc.owner.split(' ').map(n => n[0]).join('')}
              </div>
              <div className="h-4 w-[1px] bg-clickup-border mx-1" />
              <button onClick={handleBack} className="p-1.5 hover:bg-red-500/20 hover:text-red-500 rounded text-gray-500 transition-colors">
                <X size={20} />
              </button>
            </div>
          </div>

          <div className="flex-1 flex overflow-hidden">
            {/* Document Sidebar (Pages) */}
            <div className="w-60 border-r border-clickup-border bg-clickup-sidebar flex flex-col overflow-hidden">
              <div className="p-4 space-y-6">
                <div className="space-y-1">
                  <h2 className="app-text-title-md px-2 text-clickup-text">{selectedDoc.title}</h2>
                </div>
                
                <div className="space-y-4">
                  <div className="space-y-1">
                    <div className="flex items-center justify-between px-2 mb-2">
                      <span className="app-text-overline text-gray-500">Pages</span>
                    </div>
                    <div className="space-y-0.5 overflow-y-auto custom-scrollbar max-h-[calc(100vh-250px)]">
                      {selectedDoc.pages.map(page => (
                        <button
                          key={page.id}
                          onClick={() => setSelectedPageId(page.id)}
                          className={cn(
                            "app-text-body-sm group flex w-full items-center gap-2 rounded px-3 py-1.5 transition-all",
                            selectedPageId === page.id 
                              ? "bg-clickup-purple/10 text-clickup-purple" 
                              : "text-gray-400 hover:bg-clickup-hover hover:text-gray-200"
                          )}
                        >
                          <FileText size={14} className={selectedPageId === page.id ? "text-clickup-purple" : "text-gray-500"} />
                          <span className="truncate flex-1 text-left">{page.title}</span>
                          <MoreHorizontal size={14} className="opacity-0 group-hover:opacity-100 text-gray-500" />
                        </button>
                      ))}
                      <button className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 transition-all hover:bg-clickup-hover hover:text-clickup-purple">
                        <Plus size={14} />
                        <span>Add page</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-auto p-4 border-t border-clickup-border space-y-1">
                <button className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 hover:bg-clickup-hover">
                  <Settings size={14} />
                  <span>Doc Settings</span>
                </button>
                <button className="app-text-body-sm flex w-full items-center gap-2 rounded px-3 py-1.5 text-gray-500 hover:bg-clickup-hover">
                  <Trash2 size={14} />
                  <span>Archive Doc</span>
                </button>
              </div>
            </div>

            {/* Editor Content Area */}
            <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-[#1e1e24] overflow-y-auto custom-scrollbar">
              <div className="max-w-4xl mx-auto py-12 px-12 w-full">
                <div className="space-y-6">
                  <div className="app-text-caption flex items-center gap-2 text-gray-500">
                    <LinkIcon size={12} className="rotate-45" />
                    <span>Link Task or Doc</span>
                  </div>
                  
                  <div className="space-y-4">
                    <h1 className="app-text-title-xl text-clickup-text outline-none" contentEditable suppressContentEditableWarning>
                      {activePage?.title}
                    </h1>
                    
                    <div className="app-text-caption flex items-center gap-3 text-gray-500">
                      <div className="flex items-center gap-1.5">
                        <div className="app-text-micro flex h-5 w-5 items-center justify-center rounded-full bg-clickup-purple font-bold text-white">
                          {selectedDoc.owner.split(' ').map(n => n[0]).join('')}
                        </div>
                        <span className="app-text-control text-clickup-text">{selectedDoc.owner}</span>
                      </div>
                      <span>•</span>
                      <div className="flex items-center gap-1">
                        <span>Last updated Today at 10:18 pm</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-4 pt-4">
                    <button className="app-text-control-sm flex items-center gap-2 text-gray-500 hover:text-gray-300">
                      <FileText size={14} />
                      <span>Start writing</span>
                    </button>
                    <button className="app-text-control-sm flex items-center gap-2 text-gray-500 hover:text-gray-300">
                      <Files size={14} />
                      <span>Blank wiki</span>
                    </button>
                    <button className="app-text-control-sm flex items-center gap-2 text-clickup-purple hover:opacity-80">
                      <Sparkles size={14} />
                      <span>Write with AI</span>
                    </button>
                  </div>

                  <div className="space-y-4 pt-8">
                    <span className="app-text-overline text-gray-500">Add new</span>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { icon: Files, label: 'Table' },
                        { icon: Activity, label: 'Column' },
                        { icon: Files, label: 'ClickUp List' },
                        { icon: FileText, label: 'Subpage' },
                      ].map(item => (
                        <button key={item.label} className="app-text-body-sm flex items-center gap-3 rounded-md p-2 text-gray-400 transition-colors hover:bg-clickup-hover">
                          <item.icon size={14} />
                          <span>{item.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="prose dark:prose-invert max-w-none pt-8">
                    <BlockEditor placeholder="Start writing..." uploadFile={uploadFile} resolveFileUrl={resolveFileUrl} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
    );
  };

  // Main Render
  return (
    <div className="h-full w-full flex flex-col min-w-0 bg-clickup-bg overflow-hidden relative">
      <AnimatePresence mode="wait">
        {!docId ? (
          <motion.div 
            key="list"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex flex-col overflow-hidden"
          >
            <div className="p-8 space-y-6 overflow-y-auto h-full custom-scrollbar">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <h1 className="app-text-title-lg text-clickup-text">{activeCategory}</h1>
                  <p className="app-text-caption text-gray-500">Manage and organize your documents and wikis</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative mr-2">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
                    <input 
                      type="text" 
                      placeholder="Search docs..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="app-text-body-sm w-64 rounded-md border border-clickup-border bg-clickup-sidebar py-2 pl-9 pr-4 text-clickup-text focus:border-clickup-purple focus:outline-none"
                    />
                  </div>
                  <button className="app-text-control flex items-center gap-2 rounded-md bg-clickup-purple px-4 py-2 text-white shadow-lg shadow-purple-500/20 transition-opacity hover:opacity-90">
                    <Plus size={16} />
                    <span>New Doc</span>
                  </button>
                  <button className="app-text-control rounded-md border border-clickup-border px-4 py-2 text-clickup-text transition-colors hover:bg-clickup-hover">
                    New Wiki
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-4 border-b border-clickup-border pb-2">
                <button className="app-text-control-sm flex items-center gap-1.5 rounded px-2 py-1 text-gray-500 hover:bg-clickup-hover hover:text-clickup-text">
                  <Filter size={14} />
                  <span>Filters</span>
                </button>
                <button className="app-text-control-sm flex items-center gap-1.5 rounded px-2 py-1 text-gray-500 hover:bg-clickup-hover hover:text-clickup-text">
                  <Activity size={14} />
                  <span>Sort</span>
                </button>
                <div className="app-text-caption ml-auto flex items-center gap-2 text-gray-500">
                  <span>Tags:</span>
                  <button className="px-2 py-0.5 bg-clickup-sidebar border border-clickup-border rounded hover:bg-clickup-hover">View all</button>
                </div>
              </div>

              {filteredDocs.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                  {filteredDocs.map(doc => (
                    <motion.div 
                      key={doc.id} 
                      layoutId={doc.id}
                      onClick={() => handleDocClick(doc.id)}
                      className="card hover:border-clickup-purple transition-all cursor-pointer group flex flex-col gap-4"
                    >
                      <div className="h-32 bg-clickup-sidebar rounded-md border border-clickup-border flex items-center justify-center group-hover:bg-clickup-hover transition-colors relative overflow-hidden">
                        <FileText size={32} className="text-gray-600 group-hover:text-clickup-purple relative z-10" />
                        <div className="absolute inset-0 bg-gradient-to-br from-clickup-purple/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                        <div className="absolute top-2 right-2">
                          <Star size={14} className={cn("text-gray-600 hover:text-yellow-500", doc.favorite && "text-yellow-500 fill-yellow-500")} />
                        </div>
                      </div>
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="app-text-control truncate text-clickup-text">{doc.title}</h3>
                          <span className="app-text-micro rounded border border-clickup-border bg-clickup-sidebar px-1.5 py-0.5 text-gray-500">
                            {doc.pages.length} {doc.pages.length === 1 ? 'page' : 'pages'}
                          </span>
                        </div>
                        <div className="flex items-center justify-between mt-2">
                          <div className="flex items-center gap-1.5">
                            <div className="app-text-micro flex h-4 w-4 items-center justify-center rounded-full bg-clickup-purple font-bold text-white">
                              {doc.owner.split(' ').map(n => n[0]).join('')}
                            </div>
                            <span className="app-text-micro text-gray-500">{doc.owner}</span>
                          </div>
                          <span className="app-text-micro text-gray-600">{doc.date}</span>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center py-20 text-center">
                  <div className="w-24 h-24 bg-clickup-sidebar rounded-full flex items-center justify-center mb-6">
                    <FileSearch size={48} className="text-gray-600 opacity-20" />
                  </div>
                  <h2 className="app-text-title-md mb-2 text-clickup-text">No Docs found</h2>
                  <p className="app-text-body mb-8 max-w-xs mx-auto text-gray-500">
                    Create anything from project plans to knowledge bases with Docs
                  </p>
                  <div className="flex items-center gap-3">
                    <button className="app-text-control rounded-md bg-clickup-purple px-6 py-2 font-bold text-white transition-opacity hover:opacity-90">
                      New Doc
                    </button>
                    <button className="app-text-control rounded-md border border-clickup-border px-6 py-2 font-bold text-clickup-text transition-colors hover:bg-clickup-hover">
                      New Wiki
                    </button>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.div
            key="editor"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 z-50 flex flex-col bg-clickup-bg overflow-hidden"
          >
            {renderEditor()}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
