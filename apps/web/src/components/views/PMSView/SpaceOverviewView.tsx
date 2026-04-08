import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Layout,
  FileText,
  FolderOpen,
  FolderKanban,
  ChevronRight,
  Plus,
  Loader2,
} from 'lucide-react';
import { Panel } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listPmsLists,
  listFolders,
  listSpaceDocPages,
  type PmsList,
  type PmsFolder,
  type PmsSpaceDocPage,
} from '@/src/domains/pms/pms-api';
import { CreateProjectModal } from './CreateProjectModal';

export const SpaceOverviewView = ({
  spaceId,
  spaceName,
}: {
  spaceId: string;
  spaceName?: string | null;
}) => {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [lists, setLists] = useState<PmsList[]>([]);
  const [folders, setFolders] = useState<PmsFolder[]>([]);
  const [docPages, setDocPages] = useState<PmsSpaceDocPage[]>([]);
  const [loading, setLoading] = useState(true);
  const [createListOpen, setCreateListOpen] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);

    Promise.all([
      listPmsLists(token, spaceId),
      listFolders(token, spaceId),
      listSpaceDocPages(token, spaceId).catch(() => ({ items: [] as PmsSpaceDocPage[] })),
    ])
      .then(([listRes, folderRes, docRes]) => {
        if (cancelled) return;
        setLists(listRes.items);
        setFolders(folderRes.items);
        setDocPages(docRes.items);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [spaceId, token]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 size={24} className="animate-spin text-clickup-purple" />
      </div>
    );
  }

  const rootLists = lists.filter((l) => !l.folder_id);
  const folderMap = new Map(folders.map((f) => [f.id, f]));
  const listsByFolder = new Map<string, PmsList[]>();
  for (const list of lists) {
    if (list.folder_id && folderMap.has(list.folder_id)) {
      const arr = listsByFolder.get(list.folder_id) ?? [];
      arr.push(list);
      listsByFolder.set(list.folder_id, arr);
    }
  }

  return (
    <div className="h-full flex flex-col">
      <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-clickup-purple rounded flex items-center justify-center text-white">
            <Layout size={20} />
          </div>
          <div>
            <h1 className="app-text-title-lg text-clickup-text">{spaceName ?? 'Space'}</h1>
            <div className="app-text-micro text-gray-500">
              {lists.length} lists · {folders.length} folders · {docPages.length} docs
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <div className="max-w-5xl mx-auto space-y-8">
          {/* Docs */}
          <Panel>
            <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-clickup-text">
              <FileText size={16} className="text-clickup-purple" />
              Docs
            </h3>
            <div className="space-y-2">
              {docPages.slice(0, 8).map((page) => (
                <div
                  key={page.id}
                  onClick={() => navigate(`/tool/pms-space-${spaceId}-docs/${page.id}`)}
                  className="flex items-center gap-3 p-2 hover:bg-clickup-hover rounded-md cursor-pointer group"
                >
                  <FileText size={14} className="text-gray-500 shrink-0" />
                  <span className="app-text-body-sm flex-1 truncate text-clickup-text transition-colors group-hover:text-clickup-purple">
                    {page.title}
                  </span>
                </div>
              ))}
              {docPages.length === 0 && (
                <p className="app-text-body text-clickup-text/40">No docs yet</p>
              )}
              {docPages.length > 0 && (
                <button
                  onClick={() => navigate(`/tool/pms-space-${spaceId}-docs`)}
                  className="app-text-control-sm text-clickup-purple transition-colors hover:text-clickup-purple/80"
                >
                  View all docs
                </button>
              )}
            </div>
          </Panel>

          {/* Folders */}
          {folders.length > 0 && (
            <Panel>
              <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-clickup-text">
                <FolderOpen size={16} className="text-clickup-purple" />
                Folders
              </h3>
              <div className="space-y-3">
                {folders.map((folder) => {
                  const folderLists = listsByFolder.get(folder.id) ?? [];
                  return (
                    <div key={folder.id} className="space-y-1">
                      <div className="app-text-body-sm flex items-center gap-2 font-medium text-clickup-text">
                        <FolderOpen size={14} className="text-amber-400" />
                        {folder.name}
                      </div>
                      {folderLists.map((list) => (
                        <div
                          key={list.id}
                          onClick={() => navigate(`/tool/pms-list-${list.id}`)}
                          className="flex items-center gap-3 pl-6 p-2 hover:bg-clickup-hover rounded-md cursor-pointer group"
                        >
                          <FolderKanban size={14} className="text-blue-400 shrink-0" />
                          <span className="app-text-body-sm flex-1 truncate text-clickup-text transition-colors group-hover:text-clickup-purple">
                            {list.name}
                          </span>
                          <span className="app-text-micro text-clickup-text/30">
                            {list.issue_count} issues
                          </span>
                          <ChevronRight size={12} className="text-clickup-text/30 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </Panel>
          )}

          {/* Lists */}
          <Panel>
            <h3 className="app-text-title-md mb-4 flex items-center justify-between text-clickup-text">
              <div className="flex items-center gap-2">
                <FolderKanban size={16} className="text-clickup-purple" />
                Lists
              </div>
              <button
                onClick={() => setCreateListOpen(true)}
                className="app-text-control-sm flex items-center gap-1 text-clickup-purple transition-colors hover:text-clickup-purple/80"
              >
                <Plus size={14} />
                <span>New List</span>
              </button>
            </h3>
            <div className="space-y-2">
              {rootLists.map((list) => (
                <div
                  key={list.id}
                  onClick={() => navigate(`/tool/pms-list-${list.id}`)}
                  className="flex items-center gap-3 p-2 hover:bg-clickup-hover rounded-md cursor-pointer group"
                >
                  <FolderKanban size={14} className="text-blue-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="app-text-body-sm truncate font-medium text-clickup-text transition-colors group-hover:text-clickup-purple">
                      {list.name}
                    </div>
                    <div className="app-text-micro text-clickup-text/40">
                      {list.issue_count} issues · {Math.round(list.progress * 100)}% done
                    </div>
                  </div>
                  <ChevronRight size={14} className="text-clickup-text/30 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              ))}
              {rootLists.length === 0 && (
                <p className="app-text-body text-clickup-text/40">No lists yet</p>
              )}
            </div>
          </Panel>
        </div>
      </main>

      <CreateProjectModal
        isOpen={createListOpen}
        onClose={() => setCreateListOpen(false)}
        teamId={spaceId}
        onCreated={(project) => {
          setLists((current) => [...current, project]);
          navigate(`/tool/pms-list-${project.id}`);
        }}
      />
    </div>
  );
};
