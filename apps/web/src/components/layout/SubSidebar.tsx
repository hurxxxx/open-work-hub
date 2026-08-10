import {
  Fragment,
  useCallback,
  useState,
  useEffect,
  useMemo,
  useRef,
  type RefObject,
  type SetStateAction,
} from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { AnimatePresence, LazyMotion, domAnimation, m } from 'motion/react';
import { ChevronDown, ChevronRight, Pin, PinOff, Plus } from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  hasWorkspaceMembership,
  type AuthUser,
} from '@/src/platform/auth/auth-api';
import { resolveNavItemHref } from '@/src/platform/workspaces/workspace-utils';
import type {
  WorkspaceBootstrapApp,
  WorkspaceBootstrapNavItem,
} from '@/src/platform/workspaces/workspaces-api';
import type { AdminSectionAccessResolver } from '@/src/platform/admin/admin-permissions';
import type {
  AppBarItem,
  AppModuleId,
  LauncherGlobalPaths,
  NavItem,
} from '@/src/app/shell/navigation-types';
import { EMPTY_LAUNCHER_GLOBAL_PATHS } from '@/src/app/shell/navigation-types';
import type {
  AppSidebarConfig,
  AppSidebarCreateAction,
  AppSidebarActionContext,
  AppSidebarRenderContext,
} from '@/src/app/shell/sidebar-types';
import {
  calculateSubSidebarCreateMenuPosition,
  isSubSidebarCreateMenuOpen,
  restoreSubSidebarWidth,
  setSubSidebarCreateMenuOpen,
  widthFromSubSidebarPointer,
  SUB_SIDEBAR_DEFAULT_WIDTH,
} from './sub-sidebar-frame-model';
import { resolveActiveFeatureAppId } from './sub-sidebar-feature-model';
import {
  buildSubSidebarNavigationProjection,
  normalizeSubSidebarCategoryExpansionState,
  toggleSubSidebarCategoryExpansion,
  type SubSidebarCategoryExpansionState,
} from './sub-sidebar-navigation-model';
import { resolveSubSidebarTitle } from './sub-sidebar-title-model';

const getNoopAppSidebarConfig = () => null;

function SubSidebarHeader({
  activeAppId,
  activeFeatureAppId,
  appBarItems,
  createActions,
  createButtonRef,
  createMenuOpen,
  createMenuPosition,
  createMenuRef,
  isMobile,
  onCloseCreateMenu,
  onNavigate,
  onPinnedChange,
  onToggleCreateMenu,
  pinned,
  sidebarActionContext,
  workspaceAppRegistry,
}: {
  activeAppId: string;
  activeFeatureAppId: string | null;
  appBarItems: readonly AppBarItem[];
  createActions: AppSidebarCreateAction[];
  createButtonRef: RefObject<HTMLButtonElement | null>;
  createMenuOpen: boolean;
  createMenuPosition: { left: number; top: number } | null;
  createMenuRef: RefObject<HTMLDivElement | null>;
  isMobile: boolean;
  onCloseCreateMenu: () => void;
  onNavigate?: () => void;
  onPinnedChange?: (pinned: boolean) => void;
  onToggleCreateMenu: () => void;
  pinned: boolean;
  sidebarActionContext: AppSidebarActionContext;
  workspaceAppRegistry: Map<string, WorkspaceBootstrapApp>;
}) {
  const { t } = useTranslation('shell');
  const appTitle = resolveSubSidebarTitle({
    activeAppId,
    activeFeatureAppId,
    appBarItems,
    t,
    workspaceAppRegistry,
  });

  return (
    <div className="flex items-center justify-between border-b border-app-border p-4">
      <h2 className="app-text-overline text-app-ink/70 dark:text-app-ink/80">
        {appTitle}
      </h2>
      <div className="flex items-center gap-1.5">
        {createActions.length > 0 ? (
          <div ref={createMenuRef} className="relative">
            <button
              ref={createButtonRef}
              type="button"
              onClick={onToggleCreateMenu}
              title={t('sidebar.create')}
              className="flex size-8 items-center justify-center rounded-md border border-app-border bg-app-surface text-app-ink shadow-sm transition-colors hover:bg-app-surface-hover"
            >
              <Plus size={16} />
            </button>
            {createMenuOpen ? (
              <div
                className="fixed z-50 w-52 rounded-lg border border-app-border bg-app-surface py-1 shadow-xl"
                style={{
                  left: createMenuPosition?.left ?? 0,
                  top: createMenuPosition?.top ?? 0,
                }}
              >
                <div className="app-text-overline px-3 pt-1.5 pb-1 text-app-ink/55">
                  {t('sidebar.create')}
                </div>
                {createActions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <button
                      key={action.id}
                      type="button"
                      onClick={() => {
                        onCloseCreateMenu();
                        action.run(sidebarActionContext);
                        onNavigate?.();
                      }}
                      className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover"
                    >
                      <Icon size={14} className="text-app-ink/55" />
                      <span>
                        {t(action.labelKey ?? `sidebarActions.${action.id}`, {
                          defaultValue: action.label,
                        })}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : null}
        {!isMobile && onPinnedChange ? (
          <button
            type="button"
            onClick={() => onPinnedChange(!pinned)}
            title={pinned ? t('sidebar.unpin') : t('sidebar.pin')}
            aria-label={pinned ? t('sidebar.unpin') : t('sidebar.pin')}
            className={cn(
              'flex size-8 items-center justify-center rounded-md border shadow-sm transition-colors',
              pinned
                ? 'border-app-accent/45 bg-app-accent/15 text-app-accent hover:bg-app-accent/20'
                : 'border-app-border bg-app-surface text-app-ink/70 hover:border-app-accent/40 hover:bg-app-accent/10 hover:text-app-accent',
            )}
          >
            {pinned ? <PinOff size={15} /> : <Pin size={15} />}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function SidebarCategorySection({
  activeNavItemId,
  category,
  currentWorkspaceSlug,
  expanded,
  filteredItems,
  launcherGlobalPaths,
  onNavigate,
  onToggleCategory,
  user,
}: {
  activeNavItemId: string;
  category: string;
  currentWorkspaceSlug: string | null;
  expanded: boolean;
  filteredItems: NavItem[];
  launcherGlobalPaths: LauncherGlobalPaths;
  onNavigate?: () => void;
  onToggleCategory: (category: string) => void;
  user: AuthUser | null;
}) {
  const { t } = useTranslation('shell');
  return (
    <div className="space-y-1">
      <button
        type="button"
        onClick={() => onToggleCategory(category)}
        className="sidebar-section-label sidebar-section-header group/section flex w-full items-center gap-1 px-3 py-1"
      >
        {expanded ? (
          <ChevronDown
            size={11}
            className="text-app-ink/55 transition-colors group-hover/section:text-app-ink dark:text-app-ink/65 dark:group-hover/section:text-white"
          />
        ) : (
          <ChevronRight
            size={11}
            className="text-app-ink/55 transition-colors group-hover/section:text-app-ink dark:text-app-ink/65 dark:group-hover/section:text-white"
          />
        )}
        <span>{category}</span>
      </button>

      <LazyMotion features={domAnimation}>
        <AnimatePresence initial={false}>
          {expanded ? (
            <m.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              {filteredItems.map((item) => {
                if (item.category !== category) {
                  return null;
                }
                return (
                  <Link
                    key={item.id}
                    to={resolveNavItemHref(
                      item,
                      currentWorkspaceSlug,
                      user,
                      launcherGlobalPaths,
                    )}
                    className={cn(
                      'sidebar-submenu-item ml-1',
                      activeNavItemId === item.id &&
                        'sidebar-submenu-item-active',
                      item.comingSoon && 'opacity-60',
                    )}
                    onClick={onNavigate}
                  >
                    <item.icon
                      size={16}
                      className="text-app-ink/55 dark:text-app-ink/65"
                    />
                    <span className="sidebar-submenu-label">{item.title}</span>
                    {item.comingSoon ? (
                      <span className="ml-auto rounded border border-app-border bg-app-bg px-1.5 py-0.5 text-[12px] uppercase tracking-wide text-app-ink/55">
                        {t('sidebar.comingSoon')}
                      </span>
                    ) : null}
                  </Link>
                );
              })}
            </m.div>
          ) : null}
        </AnimatePresence>
      </LazyMotion>
    </div>
  );
}

function SidebarCategoryList({
  activeNavItemId,
  categories,
  currentWorkspaceSlug,
  expandedCategories,
  filteredItems,
  launcherGlobalPaths,
  onNavigate,
  sidebarConfig,
  sidebarContext,
  toggleCategory,
  user,
}: {
  activeNavItemId: string;
  categories: string[];
  currentWorkspaceSlug: string | null;
  expandedCategories: string[];
  filteredItems: NavItem[];
  launcherGlobalPaths: LauncherGlobalPaths;
  onNavigate?: () => void;
  sidebarConfig: AppSidebarConfig | null | undefined;
  sidebarContext: AppSidebarRenderContext;
  toggleCategory: (category: string) => void;
  user: AuthUser | null;
}) {
  return (
    <div className="custom-scrollbar flex-1 space-y-6 overflow-y-auto px-2 py-4">
      {sidebarConfig?.beforeCategories?.(sidebarContext)}
      {categories.map((category) => {
        const customCategory = sidebarConfig?.renderCategory?.(
          category,
          sidebarContext,
        );
        if (customCategory !== undefined) {
          return <Fragment key={category}>{customCategory}</Fragment>;
        }

        return (
          <SidebarCategorySection
            key={category}
            activeNavItemId={activeNavItemId}
            category={category}
            currentWorkspaceSlug={currentWorkspaceSlug}
            expanded={expandedCategories.includes(category)}
            filteredItems={filteredItems}
            launcherGlobalPaths={launcherGlobalPaths}
            onNavigate={onNavigate}
            onToggleCategory={toggleCategory}
            user={user}
          />
        );
      })}
      {sidebarConfig?.afterCategories?.(sidebarContext)}
    </div>
  );
}

function SidebarResizeHandle({
  isResizing,
  onStartResize,
}: {
  isResizing: boolean;
  onStartResize: () => void;
}) {
  const { t } = useTranslation('shell');
  return (
    <button
      type="button"
      aria-label={t('sidebar.resize', { defaultValue: 'Resize sidebar' })}
      onMouseDown={(event) => {
        event.preventDefault();
        onStartResize();
      }}
      className={cn(
        'absolute right-0 top-0 h-full w-1 cursor-col-resize border-0 bg-transparent p-0 transition-colors hover:bg-app-accent/30',
        isResizing && 'bg-app-accent/50',
      )}
      title={t('sidebar.resize', { defaultValue: 'Resize sidebar' })}
    />
  );
}

type SubSidebarFrameState = {
  createButtonRef: RefObject<HTMLButtonElement | null>;
  createMenuOpen: boolean;
  createMenuPosition: { left: number; top: number } | null;
  createMenuRef: RefObject<HTMLDivElement | null>;
  sidebarRef: RefObject<HTMLDivElement | null>;
  sidebarWidth: number;
  isResizing: boolean;
  closeCreateMenu: () => void;
  startResize: () => void;
  toggleCreateMenu: () => void;
};

function useSubSidebarFrameState(activeAppId: string): SubSidebarFrameState {
  const [createMenuState, setCreateMenuState] = useState<{
    appId: string;
    open: boolean;
  }>({ appId: activeAppId, open: false });
  const createMenuOpen = isSubSidebarCreateMenuOpen(
    createMenuState,
    activeAppId,
  );
  const setCreateMenuOpen = useCallback(
    (nextOpen: SetStateAction<boolean>) => {
      setCreateMenuState((prev) => {
        return setSubSidebarCreateMenuOpen(prev, activeAppId, nextOpen);
      });
    },
    [activeAppId],
  );
  const closeCreateMenu = useCallback(
    () => setCreateMenuOpen(false),
    [setCreateMenuOpen],
  );
  const closeCreateMenuRef = useRef<() => void>(() => undefined);
  closeCreateMenuRef.current = closeCreateMenu;
  const [createMenuPosition, setCreateMenuPosition] = useState<{
    left: number;
    top: number;
  } | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const createMenuRef = useRef<HTMLDivElement>(null);
  const createButtonRef = useRef<HTMLButtonElement>(null);

  const updateCreateMenuPosition = useCallback(() => {
    const sidebar = sidebarRef.current;
    const button = createButtonRef.current;
    if (!sidebar || !button) return;

    setCreateMenuPosition(
      calculateSubSidebarCreateMenuPosition({
        sidebarRect: sidebar.getBoundingClientRect(),
        buttonRect: button.getBoundingClientRect(),
      }),
    );
  }, []);
  const updateCreateMenuPositionRef = useRef(updateCreateMenuPosition);
  updateCreateMenuPositionRef.current = updateCreateMenuPosition;

  useEffect(() => {
    if (!createMenuOpen) return;
    const updatePosition = () => updateCreateMenuPositionRef.current();
    function handler(event: MouseEvent) {
      if (
        createMenuRef.current &&
        !createMenuRef.current.contains(event.target as Node)
      ) {
        closeCreateMenuRef.current();
      }
    }
    document.addEventListener('mousedown', handler);
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    updatePosition();
    return () => {
      document.removeEventListener('mousedown', handler);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [createMenuOpen]);

  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return SUB_SIDEBAR_DEFAULT_WIDTH;
    return restoreSubSidebarWidth(
      window.localStorage.getItem('ai-do:sub-sidebar-width'),
    );
  });
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (event: MouseEvent) => {
      setSidebarWidth(widthFromSubSidebarPointer(event.clientX));
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
      'ai-do:sub-sidebar-width',
      String(sidebarWidth),
    );
  }, [sidebarWidth]);

  return {
    createButtonRef,
    createMenuOpen,
    createMenuPosition,
    createMenuRef,
    sidebarRef,
    sidebarWidth,
    isResizing,
    closeCreateMenu,
    startResize: () => setIsResizing(true),
    toggleCreateMenu: () => {
      updateCreateMenuPosition();
      setCreateMenuOpen((open) => !open);
    },
  };
}

type SubSidebarNavigationState = {
  categories: string[];
  createActions: AppSidebarCreateAction[];
  expandedCategories: string[];
  filteredItems: NavItem[];
  sidebarActionContext: AppSidebarActionContext;
  sidebarConfig: AppSidebarConfig | null;
  sidebarContext: AppSidebarRenderContext;
  toggleCategory: (category: string) => void;
};

function useSubSidebarNavigation({
  activeAppId,
  activeFeatureAppId,
  activeNavItemId,
  canReadTeams,
  currentWorkspaceSlug,
  enabledWorkspaceAppIds,
  getAppSidebarConfig,
  globalAppIds,
  hasAdminSectionAccess,
  locationPathname,
  navigate,
  navItems,
  onNavigate,
  user,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeFeatureAppId: string | null;
  activeNavItemId: string;
  canReadTeams: boolean;
  currentWorkspaceSlug: string | null;
  enabledWorkspaceAppIds: readonly string[];
  getAppSidebarConfig: (appId: string) => AppSidebarConfig | null;
  globalAppIds: readonly string[];
  hasAdminSectionAccess?: AdminSectionAccessResolver;
  locationPathname: string;
  navigate: ReturnType<typeof useNavigate>;
  navItems: readonly NavItem[];
  onNavigate?: () => void;
  user: AuthUser | null;
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}): SubSidebarNavigationState {
  const { t } = useTranslation('shell');
  const [expandedCategoriesState, setExpandedCategoriesState] =
    useState<SubSidebarCategoryExpansionState>({
      key: '',
      expandedCategories: [],
    });
  const sidebarConfig = getAppSidebarConfig(activeAppId);

  const navigationProjection = useMemo(
    () =>
      buildSubSidebarNavigationProjection({
        activeAppId,
        activeFeatureAppId,
        canReadWorkspace: canReadTeams,
        extendCategories: sidebarConfig?.extendCategories,
        globalAppIds,
        hasAdminSectionAccess,
        navItems,
        systemRoles: user?.system_roles ?? [],
        translate: t,
        workspaceNavItems,
      }),
    [
      activeAppId,
      activeFeatureAppId,
      canReadTeams,
      hasAdminSectionAccess,
      globalAppIds,
      sidebarConfig?.extendCategories,
      navItems,
      t,
      user?.system_roles,
      workspaceNavItems,
    ],
  );
  const { categories, filteredItems } = navigationProjection;
  const sidebarActionContext = useMemo<AppSidebarActionContext>(
    () => ({
      activeAppId: activeAppId as AppModuleId,
      activeFeatureAppId,
      currentPathname: locationPathname,
      currentWorkspaceSlug,
      enabledWorkspaceAppIds,
      navigate,
      user,
    }),
    [
      activeAppId,
      activeFeatureAppId,
      currentWorkspaceSlug,
      enabledWorkspaceAppIds,
      locationPathname,
      navigate,
      user,
    ],
  );
  const normalizedExpansionState = useMemo(
    () =>
      normalizeSubSidebarCategoryExpansionState(
        expandedCategoriesState,
        categories,
      ),
    [categories, expandedCategoriesState],
  );
  const expandedCategories = normalizedExpansionState.expandedCategories;
  const toggleCategory = useCallback(
    (category: string) => {
      setExpandedCategoriesState((prev) => {
        return toggleSubSidebarCategoryExpansion(prev, categories, category);
      });
    },
    [categories],
  );
  const isCategoryExpanded = useCallback(
    (category: string) => expandedCategories.includes(category),
    [expandedCategories],
  );
  const sidebarContext = useMemo<AppSidebarRenderContext>(
    () => ({
      ...sidebarActionContext,
      activeAppId: activeAppId as AppModuleId,
      activeFeatureAppId,
      activeNavItemId,
      canReadWorkspace: canReadTeams,
      filteredItems,
      isCategoryExpanded,
      onNavigate,
      toggleCategory,
    }),
    [
      activeAppId,
      activeFeatureAppId,
      activeNavItemId,
      canReadTeams,
      filteredItems,
      isCategoryExpanded,
      onNavigate,
      sidebarActionContext,
      toggleCategory,
    ],
  );
  const createActions = useMemo(
    () => sidebarConfig?.createActions?.(sidebarActionContext) ?? [],
    [sidebarActionContext, sidebarConfig],
  );

  return {
    categories,
    createActions,
    expandedCategories,
    filteredItems,
    sidebarActionContext,
    sidebarConfig,
    sidebarContext,
    toggleCategory,
  };
}

export const SubSidebar = ({
  activeAppId,
  activeNavItemId,
  appBarItems = [],
  currentWorkspaceSlug,
  enabledWorkspaceAppIds,
  getAppSidebarConfig = getNoopAppSidebarConfig,
  hasAdminSectionAccess,
  launcherGlobalPaths = EMPTY_LAUNCHER_GLOBAL_PATHS,
  navItems = [],
  onNavigate,
  onPinnedChange,
  overlay = false,
  pinned = false,
  variant = 'desktop',
  workspaceApps,
  workspaceNavItems,
}: {
  activeAppId: string;
  activeNavItemId: string;
  appBarItems?: readonly AppBarItem[];
  currentWorkspaceSlug: string | null;
  enabledWorkspaceAppIds?: readonly string[];
  getAppSidebarConfig?: (appId: string) => AppSidebarConfig | null;
  hasAdminSectionAccess?: AdminSectionAccessResolver;
  launcherGlobalPaths?: LauncherGlobalPaths;
  navItems?: readonly NavItem[];
  onNavigate?: () => void;
  onPinnedChange?: (pinned: boolean) => void;
  overlay?: boolean;
  pinned?: boolean;
  variant?: 'desktop' | 'mobile';
  workspaceApps: WorkspaceBootstrapApp[];
  workspaceNavItems: WorkspaceBootstrapNavItem[];
}) => {
  const { pathname: locationPathname } = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isMobile = variant === 'mobile';
  const canReadTeams = hasWorkspaceMembership(user, currentWorkspaceSlug);
  const workspaceAppRegistry = useMemo(
    () => new Map(workspaceApps.map((item) => [item.app_id, item])),
    [workspaceApps],
  );
  const fallbackEnabledWorkspaceAppIds = useMemo(
    () => workspaceApps.flatMap((item) => (item.enabled ? [item.app_id] : [])),
    [workspaceApps],
  );
  const resolvedEnabledWorkspaceAppIds =
    enabledWorkspaceAppIds ?? fallbackEnabledWorkspaceAppIds;
  const globalAppIds = useMemo(
    () => Array.from(launcherGlobalPaths.keys()),
    [launcherGlobalPaths],
  );
  const frameState = useSubSidebarFrameState(activeAppId);
  const activeFeatureAppId = useMemo(
    () =>
      resolveActiveFeatureAppId({
        activeAppId,
        activeNavItemId,
        navItems,
        pathname: locationPathname,
      }),
    [activeAppId, activeNavItemId, locationPathname, navItems],
  );
  const navigationState = useSubSidebarNavigation({
    activeAppId,
    activeFeatureAppId,
    activeNavItemId,
    canReadTeams,
    currentWorkspaceSlug,
    enabledWorkspaceAppIds: resolvedEnabledWorkspaceAppIds,
    getAppSidebarConfig,
    globalAppIds,
    hasAdminSectionAccess,
    locationPathname,
    navigate,
    navItems,
    onNavigate,
    user,
    workspaceNavItems,
  });

  if (activeAppId === 'home') {
    return null;
  }

  return (
    <div
      className={cn(
        'relative h-full flex-col overflow-hidden bg-app-surface-sidebar',
        isMobile
          ? 'flex w-full'
          : 'hidden shrink-0 border-r border-app-border lg:flex',
        !isMobile && overlay && 'shadow-2xl shadow-black/20',
      )}
      ref={frameState.sidebarRef}
      style={isMobile ? undefined : { width: `${frameState.sidebarWidth}px` }}
    >
      <SubSidebarHeader
        activeAppId={activeAppId}
        activeFeatureAppId={activeFeatureAppId}
        appBarItems={appBarItems}
        createActions={navigationState.createActions}
        createButtonRef={frameState.createButtonRef}
        createMenuOpen={frameState.createMenuOpen}
        createMenuPosition={frameState.createMenuPosition}
        createMenuRef={frameState.createMenuRef}
        isMobile={isMobile}
        onCloseCreateMenu={frameState.closeCreateMenu}
        onNavigate={onNavigate}
        onPinnedChange={onPinnedChange}
        onToggleCreateMenu={frameState.toggleCreateMenu}
        pinned={pinned}
        sidebarActionContext={navigationState.sidebarActionContext}
        workspaceAppRegistry={workspaceAppRegistry}
      />

      <SidebarCategoryList
        activeNavItemId={activeNavItemId}
        categories={navigationState.categories}
        currentWorkspaceSlug={currentWorkspaceSlug}
        expandedCategories={navigationState.expandedCategories}
        filteredItems={navigationState.filteredItems}
        launcherGlobalPaths={launcherGlobalPaths}
        onNavigate={onNavigate}
        sidebarConfig={navigationState.sidebarConfig}
        sidebarContext={navigationState.sidebarContext}
        toggleCategory={navigationState.toggleCategory}
        user={user}
      />

      {!isMobile && pinned ? (
        <SidebarResizeHandle
          isResizing={frameState.isResizing}
          onStartResize={frameState.startResize}
        />
      ) : null}
    </div>
  );
};
