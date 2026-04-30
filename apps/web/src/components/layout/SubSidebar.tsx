import { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import {
  Calendar,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Plus,
  Layout,
  FileText,
  PanelLeftClose,
  PanelLeftOpen,
  Sparkles,
  Users,
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { APP_BAR_ITEMS, NAV_ITEMS } from '@/src/app/shell/app-registry';
import {
  hasAdminSectionAccess,
  type AdminSection,
} from '@/src/domains/admin/admin-permissions';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/domains/auth/auth-api';
import { AiSidebarSection } from '@/src/app-modules/ai';
import { DocsSidebarExtras } from '@/src/app-modules/docs';
import { LearningSidebarTree } from '@/src/app-modules/learning';
import { PmsSidebarSpaces } from '@/src/app-modules/pms';
import {
  buildWorkspaceAppPath,
  resolveDefaultWorkspaceAppPath,
  resolveNavItemHref,
  resolveToolInvocationHref,
} from '@/src/domains/workspaces/workspace-utils';
import type {
  WorkspaceBootstrapApp,
  WorkspaceBootstrapNavItem,
} from '@/src/domains/workspaces/workspaces-api';
import type { NavItem } from '@/src/app/shell/navigation-types';
import { buildSidebarCategories } from './sub-sidebar-categories';

function isDefined<T>(value: T | null): value is T {
  return value !== null;
}

export const SubSidebar = ({
  activeAppId,
  activeNavItemId,
  currentWorkspaceSlug,
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  currentWorkspaceSlug: string | null;
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canReadTeams = hasWorkspaceMembership(user, currentWorkspaceSlug);
  const meetingRootPath = resolveDefaultWorkspaceAppPath(user, 'meeting');

  const [expandedCategories, setExpandedCategories] = useState<string[]>([]);
  const [createMenuOpen, setCreateMenuOpen] = useState(false);
  const createMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!createMenuOpen) return;
    function handler(event: MouseEvent) {
      if (
        createMenuRef.current &&
        !createMenuRef.current.contains(event.target as Node)
      ) {
        setCreateMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [createMenuOpen]);

  // Reset the menu when switching apps so it doesn't stay open across navigation.
  useEffect(() => {
    setCreateMenuOpen(false);
  }, [activeAppId]);

  // Resizable sidebar width (persisted in localStorage)
  const SIDEBAR_MIN_WIDTH = 180;
  const SIDEBAR_MAX_WIDTH = 480;
  const SIDEBAR_DEFAULT_WIDTH = 240;
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return SIDEBAR_DEFAULT_WIDTH;
    const saved = window.localStorage.getItem('aidoo:sub-sidebar-width');
    const parsed = saved ? parseInt(saved, 10) : NaN;
    if (
      Number.isFinite(parsed) &&
      parsed >= SIDEBAR_MIN_WIDTH &&
      parsed <= SIDEBAR_MAX_WIDTH
    ) {
      return parsed;
    }
    return SIDEBAR_DEFAULT_WIDTH;
  });
  const [isResizing, setIsResizing] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem('aidoo:sub-sidebar-collapsed') === '1';
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(
      'aidoo:sub-sidebar-collapsed',
      isCollapsed ? '1' : '0',
    );
  }, [isCollapsed]);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      // SubSidebar starts after the AppBar (w-16 = 64px)
      const newWidth = Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, e.clientX - 64),
      );
      setSidebarWidth(newWidth);
    };
    const handleMouseUp = () => {
      setIsResizing(false);
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(
      'aidoo:sub-sidebar-width',
      String(sidebarWidth),
    );
  }, [sidebarWidth]);

  const navItemRegistry = useMemo(
    () => new Map(NAV_ITEMS.map((item) => [item.id, item])),
    [],
  );
  const workspaceAppRegistry = useMemo(
    () => new Map(workspaceApps.map((item) => [item.app_id, item])),
    [workspaceApps],
  );

  const filteredItems = useMemo(() => {
    if (activeAppId !== 'settings') {
      return workspaceNavItems
        .filter((item) => item.app_id === activeAppId)
        .map((item) => {
          const localItem = navItemRegistry.get(item.id);
          if (!localItem) {
            return null;
          }
          const nextItem: NavItem = {
            ...localItem,
            title: item.title,
            category: item.category,
          };
          if (item.path_suffix !== undefined && item.path_suffix !== null) {
            nextItem.pathSuffix = item.path_suffix;
          }
          if (item.absolute_path !== undefined && item.absolute_path !== null) {
            nextItem.absolutePath = item.absolute_path;
          }
          if (item.link_app_id !== undefined && item.link_app_id !== null) {
            nextItem.linkAppId = item.link_app_id as NavItem['linkAppId'];
          }
          if (item.coming_soon) {
            nextItem.comingSoon = true;
          }
          return nextItem;
        })
        .filter(isDefined);
    }

    const items = NAV_ITEMS.filter((item) => item.appId === activeAppId);
    const sectionByItemId: Partial<Record<string, AdminSection>> = {
      'settings-general': 'general',
      'settings-people': 'people',
      'settings-workspaces': 'workspaces',
      'settings-security': 'security',
      'settings-audit': 'audit',
    };

    return items.filter((item) => {
      const section = sectionByItemId[item.id];
      return section
        ? hasAdminSectionAccess(user?.system_roles ?? [], section)
        : false;
    });
  }, [activeAppId, navItemRegistry, user?.system_roles, workspaceNavItems]);
  const categories = useMemo(
    () =>
      buildSidebarCategories(
        filteredItems.map((item) => item.category),
        activeAppId,
        canReadTeams,
      ),
    [activeAppId, canReadTeams, filteredItems],
  );

  useEffect(() => {
    setExpandedCategories(categories);
  }, [categories]);

  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) =>
      prev.includes(category)
        ? prev.filter((current) => current !== category)
        : [...prev, category],
    );
  };

  if (activeAppId === 'home') {
    return null;
  }

  return isCollapsed ? (
    <div className="relative h-full w-10 shrink-0 border-r border-app-border bg-app-surface-sidebar flex flex-col items-center pt-4">
      <button
        type="button"
        onClick={() => setIsCollapsed(false)}
        title="서브 메뉴 펼치기"
        aria-label="서브 메뉴 펼치기"
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-accent/15 hover:text-app-accent hover:border-app-accent/40"
      >
        <PanelLeftOpen size={18} />
      </button>
    </div>
  ) : (
    <div
      className="relative h-full bg-app-surface-sidebar border-r border-app-border flex flex-col overflow-hidden shrink-0"
      style={{ width: `${sidebarWidth}px` }}
    >
      <div className="flex items-center justify-between p-4 border-b border-app-border">
        <h2 className="app-text-overline text-gray-600 dark:text-gray-300">
          {activeAppId === 'settings'
            ? 'All settings'
            : (workspaceAppRegistry.get(activeAppId)?.title ??
              APP_BAR_ITEMS.find((item) => item.id === activeAppId)?.title)}
        </h2>
        <div className="flex items-center gap-1.5">
          {activeAppId === 'pms' ||
          activeAppId === 'docs' ||
          activeAppId === 'planner' ||
          activeAppId === 'ai' ||
          activeAppId === 'meeting' ? (
            <div ref={createMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setCreateMenuOpen((open) => !open)}
                title="Create"
                className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-surface-hover"
              >
                <Plus size={16} />
              </button>
              {createMenuOpen ? (
                <div className="absolute right-0 top-full mt-1 z-30 w-52 rounded-lg border border-app-border bg-app-surface py-1 shadow-xl">
                  <div className="app-text-overline px-3 pt-1.5 pb-1 text-gray-500">
                    Create
                  </div>
                  {activeAppId === 'pms' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(
                            new CustomEvent('pms:create-task'),
                          );
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <CheckSquare size={14} className="text-gray-500" />
                        <span>Task</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(
                            new CustomEvent('pms:create-space'),
                          );
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Layout size={14} className="text-gray-500" />
                        <span>Space</span>
                      </button>
                    </>
                  ) : null}
                  {activeAppId === 'docs' ? (
                    <button
                      type="button"
                      onClick={() => {
                        setCreateMenuOpen(false);
                        window.dispatchEvent(new CustomEvent('docs:create'));
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <FileText size={14} className="text-gray-500" />
                      <span>Doc</span>
                    </button>
                  ) : null}
                  {activeAppId === 'planner' ? (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(
                            new CustomEvent('planner:create-event'),
                          );
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Calendar size={14} className="text-gray-500" />
                        <span>Event</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setCreateMenuOpen(false);
                          window.dispatchEvent(
                            new CustomEvent('planner:create-meeting'),
                          );
                        }}
                        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                      >
                        <Users size={14} className="text-gray-500" />
                        <span>Meeting</span>
                      </button>
                    </>
                  ) : null}
                  {activeAppId === 'ai' ? (
                    <button
                      type="button"
                      onClick={() => {
                        setCreateMenuOpen(false);
                        const searchItem = NAV_ITEMS.find(
                          (item) => item.id === 'search',
                        );
                        navigate(
                          searchItem
                            ? resolveToolInvocationHref(
                                searchItem,
                                currentWorkspaceSlug,
                                user,
                              )
                            : '/tool/search',
                        );
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <Sparkles size={14} className="text-gray-500" />
                      <span>아이두 통합검색</span>
                    </button>
                  ) : null}
                  {activeAppId === 'meeting' ? (
                    <button
                      type="button"
                      onClick={() => {
                        setCreateMenuOpen(false);
                        if (window.location.pathname.includes('/meeting')) {
                          window.dispatchEvent(
                            new CustomEvent('meeting:create-event'),
                          );
                        } else {
                          navigate(
                            currentWorkspaceSlug
                              ? buildWorkspaceAppPath(
                                  currentWorkspaceSlug,
                                  'meeting',
                                )
                              : meetingRootPath,
                          );
                          // Defer the dispatch until after the route mounts.
                          setTimeout(() => {
                            window.dispatchEvent(
                              new CustomEvent('meeting:create-event'),
                            );
                          }, 50);
                        }
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <Users size={14} className="text-gray-500" />
                      <span>Meeting</span>
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setIsCollapsed(true)}
            title="서브 메뉴 접기"
            aria-label="서브 메뉴 접기"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-accent/15 hover:text-app-accent hover:border-app-accent/40"
          >
            <PanelLeftClose size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-4 px-2 space-y-6 custom-scrollbar">
        {activeAppId === 'ai' && currentWorkspaceSlug ? (
          <AiSidebarSection currentWorkspaceSlug={currentWorkspaceSlug} />
        ) : null}
        {categories.map((category) => {
          if (activeAppId === 'pms' && category === 'Spaces') {
            return (
              <PmsSidebarSpaces
                key={category}
                activeNavItemId={activeNavItemId}
                currentWorkspaceSlug={currentWorkspaceSlug}
                isExpanded={expandedCategories.includes('Spaces')}
                onToggle={() => toggleCategory('Spaces')}
              />
            );
          }

          return (
            <div key={category} className="space-y-1">
              <button
                onClick={() => toggleCategory(category)}
                className="sidebar-section-label sidebar-section-header group/section flex w-full items-center gap-1 px-3 py-1"
              >
                {expandedCategories.includes(category) ? (
                  <ChevronDown
                    size={11}
                    className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
                  />
                ) : (
                  <ChevronRight
                    size={11}
                    className="text-gray-500 dark:text-gray-400 transition-colors group-hover/section:text-app-ink dark:group-hover/section:text-white"
                  />
                )}
                <span>{category}</span>
              </button>

              <AnimatePresence initial={false}>
                {expandedCategories.includes(category) && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    {filteredItems
                      .filter((item) => item.category === category)
                      .map((item) => {
                        if (activeAppId === 'pms' && category === 'Personal') {
                          if (item.id === 'pms-tasks') {
                            const subTasks = filteredItems.filter(
                              (entry) =>
                                entry.category === 'Personal' &&
                                entry.id.startsWith('pms-tasks-'),
                            );
                            const isMyTasksActive =
                              activeNavItemId === 'pms-tasks' ||
                              activeNavItemId.startsWith('pms-tasks-');
                            return (
                              <div key={item.id} className="space-y-1">
                                <div
                                  className={cn(
                                    'sidebar-submenu-group ml-1 cursor-default',
                                    isMyTasksActive &&
                                      'sidebar-submenu-item-active',
                                  )}
                                >
                                  <item.icon
                                    size={16}
                                    className={cn(
                                      'text-gray-500 dark:text-gray-400',
                                      isMyTasksActive && 'text-app-accent',
                                    )}
                                  />
                                  <span className="sidebar-submenu-label">
                                    {item.title}
                                  </span>
                                </div>
                                <div className="ml-6 border-l border-app-border pl-2 space-y-1">
                                  {subTasks.map((sub) => (
                                    <Link
                                      key={sub.id}
                                      to={`/tool/${sub.id}`}
                                      className={cn(
                                        'sidebar-submenu-item',
                                        activeNavItemId === sub.id &&
                                          'sidebar-submenu-item-active',
                                      )}
                                    >
                                      <sub.icon
                                        size={14}
                                        className="text-gray-500 dark:text-gray-400"
                                      />
                                      <span className="sidebar-submenu-label">
                                        {sub.title}
                                      </span>
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
                            to={resolveNavItemHref(
                              item,
                              currentWorkspaceSlug,
                              user,
                            )}
                            className={cn(
                              'sidebar-submenu-item ml-1',
                              activeNavItemId === item.id &&
                                'sidebar-submenu-item-active',
                              item.comingSoon && 'opacity-60',
                            )}
                          >
                            <item.icon
                              size={16}
                              className="text-gray-500 dark:text-gray-400"
                            />
                            <span className="sidebar-submenu-label">
                              {item.title}
                            </span>
                            {item.comingSoon ? (
                              <span className="ml-auto rounded border border-app-border bg-app-bg px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-gray-500">
                                준비중
                              </span>
                            ) : null}
                          </Link>
                        );
                      })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}

        {activeAppId === 'docs' && (
          <DocsSidebarExtras currentWorkspaceSlug={currentWorkspaceSlug} />
        )}

        {activeAppId === 'learning' ? (
          <LearningSidebarTree currentPathname={location.pathname} />
        ) : null}
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={(e) => {
          e.preventDefault();
          setIsResizing(true);
        }}
        className={cn(
          'absolute right-0 top-0 h-full w-1 cursor-col-resize transition-colors hover:bg-app-accent/30',
          isResizing && 'bg-app-accent/50',
        )}
        title="Drag to resize"
      />
    </div>
  );
};
