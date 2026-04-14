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
  Users,
} from 'lucide-react';
import { Panel } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listPmsTaskLists,
  listFolders,
  listSpaceDocs,
  listSpaceMembers,
  listSpaces,
  type PmsTaskList,
  type PmsFolder,
  type PmsSpace,
  type PmsSpaceDoc,
  type PmsSpaceMember,
} from '@/src/domains/pms/pms-api';
import { initials } from './pms-constants';
import { CreateTaskListModal } from './CreateTaskListModal';
import { SpaceMembersModal } from './SpaceMembersModal';

const AVATAR_COLORS = [
  'bg-rose-500',
  'bg-pink-500',
  'bg-fuchsia-500',
  'bg-purple-500',
  'bg-violet-500',
  'bg-indigo-500',
  'bg-blue-500',
  'bg-sky-500',
  'bg-cyan-500',
  'bg-teal-500',
  'bg-emerald-500',
  'bg-green-500',
  'bg-amber-500',
  'bg-orange-500',
];

function avatarColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

export const SpaceOverviewView = ({
  spaceId,
  spaceName,
}: {
  spaceId: string;
  spaceName?: string | null;
}) => {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [lists, setLists] = useState<PmsTaskList[]>([]);
  const [folders, setFolders] = useState<PmsFolder[]>([]);
  const [spaceDocs, setSpaceDocs] = useState<PmsSpaceDoc[]>([]);
  const [members, setMembers] = useState<PmsSpaceMember[]>([]);
  const [spaceMeta, setSpaceMeta] = useState<PmsSpace | null>(null);
  const [loading, setLoading] = useState(true);
  const [createListOpen, setCreateListOpen] = useState(false);
  const [membersModalOpen, setMembersModalOpen] = useState(false);
  const [membersRefreshToken, setMembersRefreshToken] = useState(0);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);

    Promise.all([
      listPmsTaskLists(token, spaceId),
      listFolders(token, spaceId),
      listSpaceDocs(token, spaceId).catch(() => ({ items: [] as PmsSpaceDoc[] })),
      listSpaceMembers(token, spaceId).catch(() => ({
        items: [] as PmsSpaceMember[],
        total: 0,
        page: 1,
        page_size: 50,
      })),
      listSpaces(token).catch(() => [] as PmsSpace[]),
    ])
      .then(([listRes, folderRes, docsRes, memberRes, spaces]) => {
        if (cancelled) return;
        setLists(listRes.items);
        setFolders(folderRes.items);
        setSpaceDocs(docsRes.items);
        setMembers(memberRes.items);
        const me = Array.isArray(spaces)
          ? spaces.find((s) => s.id === spaceId) ?? null
          : null;
        setSpaceMeta(me);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [spaceId, token, membersRefreshToken]);

  const canManageMembers =
    spaceMeta?.current_user_role === 'owner' ||
    spaceMeta?.current_user_role === 'admin';

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 size={24} className="animate-spin text-app-accent" />
      </div>
    );
  }

  const rootLists = lists.filter((l) => !l.folder_id);
  const folderMap = new Map(folders.map((f) => [f.id, f]));
  const listsByFolder = new Map<string, PmsTaskList[]>();
  for (const list of lists) {
    if (list.folder_id && folderMap.has(list.folder_id)) {
      const arr = listsByFolder.get(list.folder_id) ?? [];
      arr.push(list);
      listsByFolder.set(list.folder_id, arr);
    }
  }

  return (
    <div className="h-full flex flex-col">
      <header className="bg-app-bg border-b border-app-border px-8 pt-6 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-app-accent rounded flex items-center justify-center text-app-bg">
            <Layout size={20} />
          </div>
          <div>
            <h1 className="app-text-title-lg text-app-ink">{spaceName ?? 'Space'}</h1>
            <div className="app-text-micro text-gray-500">
              {lists.length} lists · {folders.length} folders · {spaceDocs.length} doc collections
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <div className="max-w-5xl mx-auto space-y-8">
          {/* Members */}
          <Panel>
            <h3 className="app-text-title-md mb-4 flex items-center justify-between text-app-ink">
              <div className="flex items-center gap-2">
                <Users size={16} className="text-app-accent" />
                멤버 ({members.length})
              </div>
              <button
                onClick={() => setMembersModalOpen(true)}
                className="app-text-control-sm flex items-center gap-1 text-app-accent transition-colors hover:text-app-accent/80"
              >
                {canManageMembers ? (
                  <>
                    <Plus size={14} />
                    <span>멤버 관리</span>
                  </>
                ) : (
                  <span>전체 보기</span>
                )}
              </button>
            </h3>
            {members.length === 0 ? (
              <p className="app-text-body text-app-ink/40">아직 멤버가 없습니다.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {members.slice(0, 12).map((member) => (
                  <div
                    key={member.user_id}
                    title={`${member.full_name} · ${member.email}`}
                    className="inline-flex items-center gap-2 rounded-full border border-app-border bg-app-surface-sidebar py-1 pl-1 pr-3"
                  >
                    <div
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold text-white ${avatarColor(member.user_id)}`}
                    >
                      {initials(member.full_name)}
                    </div>
                    <span className="app-text-caption text-app-ink">
                      {member.full_name}
                    </span>
                    {member.role === 'owner' ? (
                      <span className="app-text-overline text-amber-500">
                        Owner
                      </span>
                    ) : member.role !== 'member' ? (
                      <span className="app-text-overline text-app-ink/40">
                        {member.role}
                      </span>
                    ) : null}
                  </div>
                ))}
                {members.length > 12 ? (
                  <button
                    type="button"
                    onClick={() => setMembersModalOpen(true)}
                    className="app-text-caption inline-flex items-center rounded-full border border-dashed border-app-border px-3 py-1 text-app-ink/60 hover:border-app-accent hover:text-app-accent"
                  >
                    +{members.length - 12} 더 보기
                  </button>
                ) : null}
              </div>
            )}
          </Panel>

          {/* Docs */}
          <Panel>
            <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-app-ink">
              <FileText size={16} className="text-app-accent" />
              Docs
            </h3>
            <div className="space-y-2">
              {spaceDocs.slice(0, 8).map((doc) => (
                <div
                  key={doc.id}
                  onClick={() => navigate(`/tool/pms-space-${spaceId}-docs-${doc.id}`)}
                  className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md cursor-pointer group"
                >
                  <FileText size={14} className="text-gray-500 shrink-0" />
                  <span className="app-text-body-sm flex-1 truncate text-app-ink transition-colors group-hover:text-app-accent">
                    {doc.title}
                  </span>
                </div>
              ))}
              {spaceDocs.length === 0 && (
                <p className="app-text-body text-app-ink/40">No doc collections yet</p>
              )}
              {spaceDocs.length > 0 && (
                <button
                  onClick={() => navigate(`/tool/pms-space-${spaceId}-docs`)}
                  className="app-text-control-sm text-app-accent transition-colors hover:text-app-accent/80"
                >
                  View all collections
                </button>
              )}
            </div>
          </Panel>

          {/* Folders */}
          {folders.length > 0 && (
            <Panel>
              <h3 className="app-text-title-md mb-4 flex items-center gap-2 text-app-ink">
                <FolderOpen size={16} className="text-app-accent" />
                Folders
              </h3>
              <div className="space-y-3">
                {folders.map((folder) => {
                  const folderLists = listsByFolder.get(folder.id) ?? [];
                  return (
                    <div key={folder.id} className="space-y-1">
                      <div className="app-text-body-sm flex items-center gap-2 font-medium text-app-ink">
                        <FolderOpen size={14} className="text-amber-400" />
                        {folder.name}
                      </div>
                      {folderLists.map((list) => (
                        <div
                          key={list.id}
                          onClick={() => navigate(`/tool/pms-list-${list.id}`)}
                          className="flex items-center gap-3 pl-6 p-2 hover:bg-app-surface-hover rounded-md cursor-pointer group"
                        >
                          <FolderKanban size={14} className="text-blue-400 shrink-0" />
                          <span className="app-text-body-sm flex-1 truncate text-app-ink transition-colors group-hover:text-app-accent">
                            {list.name}
                          </span>
                          <span className="app-text-micro text-app-ink/30">
                            {list.issue_count} issues
                          </span>
                          <ChevronRight size={12} className="text-app-ink/30 opacity-0 group-hover:opacity-100 transition-opacity" />
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
            <h3 className="app-text-title-md mb-4 flex items-center justify-between text-app-ink">
              <div className="flex items-center gap-2">
                <FolderKanban size={16} className="text-app-accent" />
                Lists
              </div>
              <button
                onClick={() => setCreateListOpen(true)}
                className="app-text-control-sm flex items-center gap-1 text-app-accent transition-colors hover:text-app-accent/80"
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
                  className="flex items-center gap-3 p-2 hover:bg-app-surface-hover rounded-md cursor-pointer group"
                >
                  <FolderKanban size={14} className="text-blue-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="app-text-body-sm truncate font-medium text-app-ink transition-colors group-hover:text-app-accent">
                      {list.name}
                    </div>
                    <div className="app-text-micro text-app-ink/40">
                      {list.issue_count} issues · {Math.round(list.progress * 100)}% done
                    </div>
                  </div>
                  <ChevronRight size={14} className="text-app-ink/30 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              ))}
              {rootLists.length === 0 && (
                <p className="app-text-body text-app-ink/40">No lists yet</p>
              )}
            </div>
          </Panel>
        </div>
      </main>

      <CreateTaskListModal
        isOpen={createListOpen}
        onClose={() => setCreateListOpen(false)}
        teamId={spaceId}
        onCreated={(taskList) => {
          setLists((current) => [...current, taskList]);
          navigate(`/tool/pms-list-${taskList.id}`);
        }}
      />

      <SpaceMembersModal
        isOpen={membersModalOpen}
        onClose={() => setMembersModalOpen(false)}
        spaceId={spaceId}
        spaceName={spaceName ?? 'Space'}
        canManage={canManageMembers}
        currentUserRole={spaceMeta?.current_user_role ?? null}
        onChanged={() => setMembersRefreshToken((v) => v + 1)}
      />
    </div>
  );
};
