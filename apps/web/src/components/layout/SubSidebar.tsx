import { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  ChevronDown,
  ChevronRight,
  Plus,
  Layout,
  Loader2,
  List as ListIcon,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { NAV_ITEMS, APP_BAR_ITEMS } from '@/src/constants';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { getWorkspaceRoleByKey } from '@/src/domains/auth/auth-api';
import { listPmsProjects, type PmsProject } from '@/src/domains/pms/pms-api';
import { listTeams, type TeamItem } from '@/src/domains/admin/admin-api';
import { CreateProjectModal } from '@/src/components/views/PMSView/CreateProjectModal';
import { CreateSpaceModal } from '@/src/components/views/PMSView/CreateSpaceModal';

const DEFAULT_SPACE_ID = '__default__';
const PMS_WORKSPACE_KEY = 'pms';
const SPACE_COLORS = [
  'bg-emerald-500',
  'bg-blue-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-violet-500',
];

function upsertProject(projects: PmsProject[], project: PmsProject): PmsProject[] {
  return [project, ...projects.filter((item) => item.id !== project.id)].sort(
    (left, right) => right.updated_at.localeCompare(left.updated_at),
  );
}

function upsertTeam(teams: TeamItem[], team: TeamItem): TeamItem[] {
  return [team, ...teams.filter((item) => item.id !== team.id)].sort(
    (left, right) => left.name.localeCompare(right.name, 'ko'),
  );
}

// ── Space "+" popover (ClickUp-style) ────────────────────────────────
const SpaceAddPopover = ({
  open,
  onClose,
  onCreateList,
}: {
  open: boolean;
  onClose: () => void;
  onCreateList: () => void;
}) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      className="absolute left-full top-0 ml-1 z-50 w-52 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1"
    >
      <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-gray-500">
        Create
      </div>
      <button
        onClick={() => { onCreateList(); onClose(); }}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-clickup-hover transition-colors"
      >
        <ListIcon size={16} className="text-gray-400" />
        <div className="text-left">
          <div className="text-xs font-medium text-clickup-text">List</div>
          <div className="text-[10px] text-clickup-text/40">Track tasks, projects & more</div>
        </div>
      </button>
    </div>
  );
};

// ── Space item in sidebar ─────────────────────────────────────────────
const SpaceItem = ({
  name,
  iconColor,
  projects,
  expanded,
  onToggle,
  onAddList,
  activeNavItemId,
  linkPath,
  isActive,
}: {
  name: string;
  iconColor: string;
  projects: PmsProject[];
  expanded: boolean;
  onToggle: () => void;
  onAddList: () => void;
  activeNavItemId: string;
  linkPath?: string;
  isActive?: boolean;
}) => {
  const [addPopoverOpen, setAddPopoverOpen] = useState(false);

  const headerClassName = cn(
    'sidebar-item flex-1 min-w-0 px-2',
    isActive && 'active',
  );

  return (
    <div className="space-y-0.5">
      <div className="group relative flex items-center gap-1">
        <button
          onClick={onToggle}
          className="ml-1 flex h-7 w-6 items-center justify-center rounded text-gray-500 transition-colors hover:bg-clickup-hover hover:text-gray-300"
          title={expanded ? 'Collapse Space' : 'Expand Space'}
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>

        {linkPath ? (
          <Link to={linkPath} className={headerClassName}>
            <div className={cn('w-5 h-5 rounded flex items-center justify-center shrink-0', iconColor)}>
              <Layout size={12} className="text-white" />
            </div>
            <span className="truncate text-xs font-medium">{name}</span>
          </Link>
        ) : (
          <button onClick={onToggle} className={headerClassName}>
            <div className={cn('w-5 h-5 rounded flex items-center justify-center shrink-0', iconColor)}>
              <Layout size={12} className="text-white" />
            </div>
            <span className="truncate text-xs font-medium">{name}</span>
          </button>
        )}

        <div className="hidden group-hover:flex items-center gap-0.5 pr-1 shrink-0">
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setAddPopoverOpen((current) => !current);
            }}
            className="p-0.5 hover:bg-clickup-hover rounded text-gray-500 hover:text-gray-300 transition-colors"
            title="Add"
          >
            <Plus size={14} />
          </button>
        </div>

        <SpaceAddPopover
          open={addPopoverOpen}
          onClose={() => setAddPopoverOpen(false)}
          onCreateList={onAddList}
        />
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="ml-4 pl-3 border-l border-clickup-border space-y-0.5">
              {projects.map((project) => (
                <Link
                  key={project.id}
                  to={`/tool/pms-project-${project.id}`}
                  className={cn(
                    'sidebar-item text-[11px] py-1 group/proj',
                    activeNavItemId === `pms-project-${project.id}` && 'active',
                  )}
                >
                  <ListIcon size={13} className="text-gray-500 shrink-0" />
                  <span className="truncate flex-1">{project.name}</span>
                  <span className="text-[10px] text-clickup-text/30 shrink-0">
                    ({project.issue_count})
                  </span>
                </Link>
              ))}
              <button
                onClick={onAddList}
                className="w-full flex items-center gap-2 px-2 py-1 text-[11px] text-gray-500 hover:text-gray-300 hover:bg-clickup-hover rounded transition-colors"
              >
                <Plus size={11} />
                <span>Add List</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// ── Main SubSidebar ───────────────────────────────────────────────────
export const SubSidebar = ({ activeAppId, activeNavItemId }: { activeAppId: string, activeNavItemId: string }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { token, user, hasPermission } = useAuth();
  const isDocEditor = location.pathname.match(/^\/tool\/[^/]+\/[^/]+$/) || location.pathname.match(/^\/docs\/[^/]+$/);
  const pmsWorkspaceId = getWorkspaceRoleByKey(user, PMS_WORKSPACE_KEY)?.workspace_id ?? null;
  const canReadTeams = hasPermission('team.read');
  const canWriteTeams = hasPermission('team.write') && Boolean(pmsWorkspaceId);

  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  const [pmsProjects, setPmsProjects] = useState<PmsProject[]>([]);
  const [pmsTeams, setPmsTeams] = useState<TeamItem[]>([]);
  const [pmsLoading, setPmsLoading] = useState(false);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [createProjectTeamId, setCreateProjectTeamId] = useState<string | null>(null);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [expandedSpaces, setExpandedSpaces] = useState<Set<string>>(new Set([DEFAULT_SPACE_ID]));

  const knownSpaceIdsRef = useRef(new Set<string>([DEFAULT_SPACE_ID]));

  const filteredItems = NAV_ITEMS.filter(item => item.appId === activeAppId);
  const categories = Array.from(new Set(filteredItems.map(item => item.category)));

  useEffect(() => {
    setExpandedCategories(categories);
  }, [activeAppId]);

  useEffect(() => {
    if (activeAppId !== 'pms' || !token) return;
    let cancelled = false;

    setPmsLoading(true);

    const projectRequest = listPmsProjects(token)
      .then((projectRes) => {
        if (cancelled) return;
        setPmsProjects(projectRes.items);
      });

    const teamRequest = canReadTeams && pmsWorkspaceId
      ? listTeams(token, pmsWorkspaceId)
          .then((teams) => {
            if (cancelled) return;
            setPmsTeams(Array.isArray(teams) ? teams : []);
          })
          .catch(() => {
            if (cancelled) return;
            setPmsTeams([]);
          })
      : Promise.resolve().then(() => {
          if (cancelled) return;
          setPmsTeams([]);
        });

    Promise.allSettled([projectRequest, teamRequest]).finally(() => {
      if (!cancelled) {
        setPmsLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [activeAppId, canReadTeams, pmsWorkspaceId, token]);

  const toggleCategory = (category: string) => {
    setExpandedCategories(prev =>
      prev.includes(category) ? prev.filter(c => c !== category) : [...prev, category]
    );
  };

  const toggleSpace = (spaceId: string) => {
    setExpandedSpaces(prev => {
      const next = new Set(prev);
      if (next.has(spaceId)) next.delete(spaceId);
      else next.add(spaceId);
      return next;
    });
  };

  const openCreateProject = (teamId: string | null) => {
    setCreateProjectTeamId(teamId);
    setCreateProjectOpen(true);
  };

  const teamSpaceActive = activeNavItemId === 'pms-space-team' || location.pathname === '/pms';

  const groupedSpaces = useMemo(() => {
    const defaultProjects: PmsProject[] = [];
    const byTeam = new Map<string, { id: string; name: string; projects: PmsProject[] }>();

    for (const project of pmsProjects) {
      if (!project.team_id) {
        defaultProjects.push(project);
        continue;
      }

      const current = byTeam.get(project.team_id) ?? {
        id: project.team_id,
        name: project.team_name ?? 'Untitled Space',
        projects: [],
      };
      current.name = project.team_name ?? current.name;
      current.projects.push(project);
      byTeam.set(project.team_id, current);
    }

    for (const team of pmsTeams) {
      const current = byTeam.get(team.id);
      if (current) {
        current.name = team.name;
      } else {
        byTeam.set(team.id, { id: team.id, name: team.name, projects: [] });
      }
    }

    return {
      defaultProjects,
      teamSpaces: Array.from(byTeam.values()).sort((left, right) => left.name.localeCompare(right.name, 'ko')),
    };
  }, [pmsProjects, pmsTeams]);

  useEffect(() => {
    setExpandedSpaces((current) => {
      const next = new Set(current);
      for (const space of groupedSpaces.teamSpaces) {
        if (!knownSpaceIdsRef.current.has(space.id)) {
          knownSpaceIdsRef.current.add(space.id);
          next.add(space.id);
        }
      }
      return next;
    });
  }, [groupedSpaces.teamSpaces]);

  if (activeAppId === 'home' || activeAppId === 'profile' || isDocEditor) return null;

  const renderPmsSpaces = () => {
    const isExpanded = expandedCategories.includes('Spaces');

    return (
      <div className="space-y-1">
        <div className="w-full flex items-center justify-between px-3 py-1">
          <button
            onClick={() => toggleCategory('Spaces')}
            className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-gray-500 hover:text-gray-300 transition-colors"
          >
            <span>Spaces</span>
            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
          {canWriteTeams && (
            <button
              onClick={() => setCreateSpaceOpen(true)}
              className="p-1 hover:bg-clickup-hover rounded text-gray-500 hover:text-gray-300 transition-colors"
              title="Create Space"
            >
              <Plus size={12} />
            </button>
          )}
        </div>

        <AnimatePresence initial={false}>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden space-y-1"
            >
              {pmsLoading ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 size={14} className="animate-spin text-gray-500" />
                </div>
              ) : (
                <>
                  <SpaceItem
                    name="Team Space"
                    iconColor="bg-clickup-purple"
                    projects={groupedSpaces.defaultProjects}
                    expanded={expandedSpaces.has(DEFAULT_SPACE_ID)}
                    onToggle={() => toggleSpace(DEFAULT_SPACE_ID)}
                    onAddList={() => openCreateProject(null)}
                    activeNavItemId={activeNavItemId}
                    linkPath="/tool/pms-space-team"
                    isActive={teamSpaceActive}
                  />

                  {groupedSpaces.teamSpaces.map((space, index) => (
                    <SpaceItem
                      key={space.id}
                      name={space.name}
                      iconColor={SPACE_COLORS[index % SPACE_COLORS.length]}
                      projects={space.projects}
                      expanded={expandedSpaces.has(space.id)}
                      onToggle={() => toggleSpace(space.id)}
                      onAddList={() => openCreateProject(space.id)}
                      activeNavItemId={activeNavItemId}
                    />
                  ))}

                  {canWriteTeams && (
                    <button
                      onClick={() => setCreateSpaceOpen(true)}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-[11px] text-gray-500 hover:text-gray-300 hover:bg-clickup-hover rounded transition-colors ml-1"
                    >
                      <Plus size={13} />
                      <span>New Space</span>
                    </button>
                  )}
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  };

  return (
    <>
      <div className="w-60 h-full bg-clickup-sidebar border-r border-clickup-border flex flex-col overflow-hidden">
        <div className="p-4 border-b border-clickup-border">
          <h2 className="text-xs font-bold uppercase tracking-widest text-gray-500">
            {activeAppId === 'settings' ? 'All settings' : APP_BAR_ITEMS.find(a => a.id === activeAppId)?.title}
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto py-4 px-2 space-y-6 custom-scrollbar">
          {categories.map(category => {
            if (activeAppId === 'pms' && category === 'Spaces') {
              return <div key={category}>{renderPmsSpaces()}</div>;
            }

            return (
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
                        // PMS Personal hierarchy (My Tasks)
                        if (activeAppId === 'pms' && category === 'Personal') {
                          if (item.id === 'pms-tasks') {
                            const subTasks = filteredItems.filter(i => i.category === 'Personal' && i.id.startsWith('pms-tasks-'));
                            const isMyTasksActive = activeNavItemId === 'pms-tasks' || activeNavItemId.startsWith('pms-tasks-');
                            return (
                              <div key={item.id} className="space-y-1">
                                <div className={cn("sidebar-item ml-1 cursor-default", isMyTasksActive && "text-clickup-text")}>
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
                          if (item.id.startsWith('pms-tasks-')) return null;
                        }

                        return (
                          <Link
                            key={item.id}
                            to={item.path ?? `/tool/${item.id}`}
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
            );
          })}
        </div>

        {activeAppId !== 'settings' && (
          <div className="p-4 border-t border-clickup-border">
            <button
              onClick={() => openCreateProject(null)}
              className="w-full flex items-center gap-2 px-3 py-2 bg-clickup-purple hover:bg-opacity-90 text-white rounded-md text-sm font-medium transition-all"
            >
              <Plus size={18} />
              <span>Quick Add</span>
            </button>
          </div>
        )}
      </div>

      <CreateProjectModal
        isOpen={createProjectOpen}
        onClose={() => setCreateProjectOpen(false)}
        teamId={createProjectTeamId}
        onCreated={(project) => {
          setPmsProjects((current) => upsertProject(current, project));
          const teamId = project.team_id;
          if (teamId) {
            knownSpaceIdsRef.current.add(teamId);
            setExpandedSpaces((current) => new Set(current).add(teamId));
          }
          navigate(`/tool/pms-project-${project.id}`);
        }}
      />

      <CreateSpaceModal
        isOpen={createSpaceOpen}
        onClose={() => setCreateSpaceOpen(false)}
        onCreated={(team) => {
          knownSpaceIdsRef.current.add(team.id);
          setPmsTeams((current) => upsertTeam(current, team));
          setExpandedSpaces((current) => new Set(current).add(team.id));
        }}
      />
    </>
  );
};
