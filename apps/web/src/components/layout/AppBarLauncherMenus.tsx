import { Check, Search, SlidersHorizontal, Star } from 'lucide-react';
import { useMemo, useState, type ReactNode, type RefObject } from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';
import type {
  WorkspaceBootstrapAppBarCategory,
  WorkspaceBootstrapAppBarCategoryItem,
} from '@/src/platform/workspaces/workspaces-api';
import { workspaceAppIconForKey } from '@/src/platform/workspaces/workspace-app-icons';
import {
  AppBarRailActiveIndicator,
  AppBarRailTooltip,
  appBarRailControlClassName,
} from './AppBarIconLink';
import { AppBarEditor } from './AppBarEditor';
import {
  type AppBarAppLinkResolver,
  type AppBarTranslator,
  type AppBarWorkspaceItem,
} from './app-bar-model';

type LauncherGridColumnCount = 3 | 4 | 5;

const launcherGridColumnClassName: Record<LauncherGridColumnCount, string> = {
  3: 'grid-cols-3',
  4: 'grid-cols-4',
  5: 'grid-cols-5',
};

const launcherPopoverWidthClassName: Record<LauncherGridColumnCount, string> = {
  3: 'w-[28rem]',
  4: 'w-[36rem]',
  5: 'w-[44rem]',
};

export function launcherGridColumnCount(
  itemCount: number,
): LauncherGridColumnCount {
  if (itemCount > 16) {
    return 5;
  }
  if (itemCount > 9) {
    return 4;
  }
  return 3;
}

export function AppBarLauncherMenus({
  appBarEditorOpen,
  appBarLayoutError,
  appBarLayoutSaving,
  categoryMenuId,
  currentPathname,
  currentWorkspaceName,
  draftItems,
  draftPinnedAppIds,
  favoritesActive,
  favoritesOpen,
  launcherCategories,
  menuRef,
  onCloseEditor,
  onCloseLauncherMenus,
  onMovePinnedApp,
  onOpenEditor,
  onResetDraft,
  onSaveLayout,
  onToggleCategoryMenu,
  onToggleFavorites,
  onTogglePinnedApp,
  pinnedEligibleAppIds,
  pinnedItems,
  resolveAppLink,
  t,
}: {
  appBarEditorOpen: boolean;
  appBarLayoutError: string | null;
  appBarLayoutSaving: boolean;
  categoryMenuId: string | null;
  currentPathname: string;
  currentWorkspaceName: string;
  draftItems: AppBarWorkspaceItem[];
  draftPinnedAppIds: WorkspaceAppId[];
  favoritesActive: boolean;
  favoritesOpen: boolean;
  launcherCategories: WorkspaceBootstrapAppBarCategory[];
  menuRef: RefObject<HTMLDivElement | null>;
  onCloseEditor: () => void;
  onCloseLauncherMenus: () => void;
  onMovePinnedApp: (appId: WorkspaceAppId, direction: -1 | 1) => void;
  onOpenEditor: () => void;
  onResetDraft: () => void;
  onSaveLayout: () => void;
  onToggleCategoryMenu: (categoryId: string) => void;
  onToggleFavorites: () => void;
  onTogglePinnedApp: (appId: WorkspaceAppId, checked: boolean) => void;
  pinnedEligibleAppIds: ReadonlySet<WorkspaceAppId>;
  pinnedItems: AppBarWorkspaceItem[];
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const visibleCategories = launcherCategories
    .map((category) => ({
      ...category,
      items: category.items.filter((item) => item.enabled),
    }))
    .filter((category) => category.items.length > 0);
  const fixedCategories = visibleCategories.filter(
    (category) => category.pinnable === false,
  );
  const customizableCategories = visibleCategories.filter(
    (category) => category.pinnable !== false,
  );
  const favoritesColumnCount = launcherGridColumnCount(pinnedItems.length);

  return (
    <div
      ref={menuRef}
      className="flex min-h-0 w-full flex-1 flex-col items-center gap-2"
    >
      <FavoritesLauncherButton
        active={favoritesActive}
        open={favoritesOpen}
        onToggle={onToggleFavorites}
        t={t}
      />
      {favoritesOpen ? (
        <LauncherPopover
          columnCount={favoritesColumnCount}
          currentWorkspaceName={currentWorkspaceName}
          iconKey="star"
          title={t('shell:appBar.favorites')}
        >
          {pinnedItems.length > 0 ? (
            <LauncherGrid columnCount={favoritesColumnCount}>
              {pinnedItems.map((item) => (
                <FavoriteLauncherItem
                  currentPathname={currentPathname}
                  item={item}
                  key={item.id}
                  onClose={onCloseLauncherMenus}
                  resolveAppLink={resolveAppLink}
                  t={t}
                />
              ))}
            </LauncherGrid>
          ) : (
            <EmptyLauncherMessage>
              {t('shell:appBar.emptyFavorites')}
            </EmptyLauncherMessage>
          )}
          <LauncherEditorButton onOpenEditor={onOpenEditor} t={t} />
        </LauncherPopover>
      ) : null}

      {fixedCategories.map((category) => {
        const activeItem = findActiveCategoryItem({
          category,
          currentPathname,
          resolveAppLink,
        });
        return (
          <CategoryLauncher
            active={
              !favoritesActive &&
              isCategoryActive({
                category,
                currentPathname,
                resolveAppLink,
              })
            }
            activeItem={activeItem}
            category={category}
            currentWorkspaceName={currentWorkspaceName}
            currentPathname={currentPathname}
            key={category.id}
            onClose={onCloseLauncherMenus}
            onToggle={() => onToggleCategoryMenu(category.id)}
            open={categoryMenuId === category.id}
            resolveAppLink={resolveAppLink}
            t={t}
          />
        );
      })}

      {customizableCategories.length > 0 ? (
        <div aria-hidden className="h-px w-8 shrink-0 bg-white/20" />
      ) : null}

      <div className="custom-scrollbar flex min-h-0 w-full flex-1 flex-col items-center gap-2 overflow-x-hidden overflow-y-auto py-0.5">
        {customizableCategories.map((category) => {
          const activeItem = findActiveCategoryItem({
            category,
            currentPathname,
            resolveAppLink,
          });
          return (
            <div
              className="flex w-full flex-col items-center gap-1.5"
              key={category.id}
            >
              <CategoryLauncher
                active={
                  !favoritesActive &&
                  isCategoryActive({
                    category,
                    currentPathname,
                    resolveAppLink,
                  })
                }
                activeItem={activeItem}
                category={category}
                currentWorkspaceName={currentWorkspaceName}
                currentPathname={currentPathname}
                onClose={onCloseLauncherMenus}
                onToggle={() => onToggleCategoryMenu(category.id)}
                open={categoryMenuId === category.id}
                resolveAppLink={resolveAppLink}
                t={t}
              />
            </div>
          );
        })}
      </div>

      {appBarEditorOpen ? (
        <AppBarEditor
          appBarLayoutError={appBarLayoutError}
          appBarLayoutSaving={appBarLayoutSaving}
          draftItems={draftItems}
          draftPinnedAppIds={draftPinnedAppIds}
          launcherCategories={customizableCategories}
          onClose={onCloseEditor}
          onMovePinnedApp={onMovePinnedApp}
          onReset={onResetDraft}
          onSave={onSaveLayout}
          onTogglePinnedApp={onTogglePinnedApp}
          pinnedEligibleAppIds={pinnedEligibleAppIds}
          t={t}
        />
      ) : null}
    </div>
  );
}

function FavoritesLauncherButton({
  active,
  onToggle,
  open,
  t,
}: {
  active: boolean;
  onToggle: () => void;
  open: boolean;
  t: AppBarTranslator;
}) {
  const label = t('shell:appBar.favorites');
  return (
    <button
      aria-expanded={open}
      aria-haspopup="menu"
      aria-label={label}
      className={appBarRailControlClassName(active || open, undefined, 'fixed')}
      onClick={onToggle}
      title={label}
      type="button"
    >
      <Star aria-hidden size={22} strokeWidth={2.25} />
      <AppBarRailTooltip title={label} />
      {active || open ? <AppBarRailActiveIndicator /> : null}
    </button>
  );
}

function CategoryLauncher({
  active,
  activeItem,
  category,
  currentWorkspaceName,
  currentPathname,
  onClose,
  onToggle,
  open,
  resolveAppLink,
  t,
}: {
  active: boolean;
  activeItem: WorkspaceBootstrapAppBarCategoryItem | null;
  category: WorkspaceBootstrapAppBarCategory;
  currentWorkspaceName: string;
  currentPathname: string;
  onClose: () => void;
  onToggle: () => void;
  open: boolean;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const Icon = workspaceAppIconForKey(
    activeItem?.icon_key ?? category.icon_key,
  );
  const title = category.title;
  const activeItemTitle = activeItem
    ? t(`shell:apps.${activeItem.app_id}`, {
        defaultValue: activeItem.title,
      })
    : null;
  const buttonTitle = activeItemTitle ? `${title} / ${activeItemTitle}` : title;
  const columnCount = launcherGridColumnCount(
    category.items.filter((item) => item.enabled).length,
  );

  return (
    <div className="relative">
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={buttonTitle}
        className={appBarRailControlClassName(
          active || open,
          undefined,
          category.pinnable === false ? 'fixed' : undefined,
        )}
        onClick={onToggle}
        title={buttonTitle}
        type="button"
      >
        <Icon aria-hidden size={22} strokeWidth={2.25} />
        <AppBarRailTooltip title={buttonTitle} />
        {active || open ? <AppBarRailActiveIndicator /> : null}
      </button>
      {open ? (
        <LauncherPopover
          columnCount={columnCount}
          currentWorkspaceName={
            category.contextLabel ??
            (category.showWorkspaceContext === false
              ? null
              : currentWorkspaceName)
          }
          iconKey={category.icon_key}
          title={title}
        >
          <CategoryItemSearch
            category={category}
            currentPathname={currentPathname}
            columnCount={columnCount}
            onClose={onClose}
            resolveAppLink={resolveAppLink}
            t={t}
          />
        </LauncherPopover>
      ) : null}
    </div>
  );
}

function CategoryItemSearch({
  category,
  columnCount,
  currentPathname,
  onClose,
  resolveAppLink,
  t,
}: {
  category: WorkspaceBootstrapAppBarCategory;
  columnCount: LauncherGridColumnCount;
  currentPathname: string;
  onClose: () => void;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const [query, setQuery] = useState('');
  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const items = category.items.filter((item) => item.enabled);
    if (!normalizedQuery) {
      return items;
    }
    return items.filter((item) => {
      const title = t(`shell:apps.${item.app_id}`, {
        defaultValue: item.title,
      });
      return `${title} ${item.app_id}`.toLowerCase().includes(normalizedQuery);
    });
  }, [category.items, query, t]);

  return (
    <>
      <label className="flex h-9 shrink-0 items-center gap-2 rounded-lg border border-app-border bg-app-bg px-2.5 text-app-ink/55 focus-within:border-app-accent focus-within:text-app-ink">
        <Search size={16} className="shrink-0" />
        <input
          aria-label={t('shell:appBar.searchApps')}
          className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/45"
          onChange={(event) => setQuery(event.currentTarget.value)}
          placeholder={t('shell:appBar.searchApps')}
          type="search"
          value={query}
        />
      </label>
      {filteredItems.length > 0 ? (
        <LauncherGrid columnCount={columnCount}>
          {filteredItems.map((item) => (
            <CategoryLauncherItem
              currentPathname={currentPathname}
              item={item}
              key={item.app_id}
              onClose={onClose}
              resolveAppLink={resolveAppLink}
              t={t}
            />
          ))}
        </LauncherGrid>
      ) : (
        <EmptyLauncherMessage>
          {query.trim()
            ? t('shell:appBar.emptySearch')
            : t('shell:appBar.emptyCategory')}
        </EmptyLauncherMessage>
      )}
    </>
  );
}

function LauncherPopover({
  children,
  columnCount = 3,
  currentWorkspaceName,
  iconKey,
  title,
}: {
  children: ReactNode;
  columnCount?: LauncherGridColumnCount;
  currentWorkspaceName: string | null;
  iconKey: string;
  title: string;
}) {
  const Icon = workspaceAppIconForKey(iconKey);
  return (
    <div
      className={cn(
        'fixed left-[5.75rem] top-4 z-50 flex max-h-[calc(100dvh-2rem)] max-w-[calc(100vw-7rem)] flex-col gap-3 overflow-hidden rounded-xl border border-app-border bg-app-surface p-3 shadow-2xl',
        launcherPopoverWidthClassName[columnCount],
      )}
      role="menu"
    >
      <div className="flex shrink-0 items-center gap-3 border-b border-app-border pb-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg border border-app-border bg-app-bg text-app-accent">
          <Icon size={21} />
        </span>
        <div className="min-w-0">
          <div className="app-text-body-sm font-semibold text-app-ink">
            {title}
          </div>
          {currentWorkspaceName ? (
            <div className="app-text-caption truncate text-app-ink/55">
              {currentWorkspaceName}
            </div>
          ) : null}
        </div>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {children}
      </div>
    </div>
  );
}

function LauncherGrid({
  children,
  columnCount,
}: {
  children: ReactNode;
  columnCount: LauncherGridColumnCount;
}) {
  return (
    <div className={cn('grid gap-2', launcherGridColumnClassName[columnCount])}>
      {children}
    </div>
  );
}

function FavoriteLauncherItem({
  currentPathname,
  item,
  onClose,
  resolveAppLink,
  t,
}: {
  currentPathname: string;
  item: AppBarWorkspaceItem;
  onClose: () => void;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const link = resolveAppLink(item.id);
  return (
    <LauncherLink
      active={isLauncherPathActive({ currentPathname, link })}
      icon={item.icon}
      onClose={onClose}
      title={item.title}
      to={link}
      t={t}
    />
  );
}

function CategoryLauncherItem({
  currentPathname,
  item,
  onClose,
  resolveAppLink,
  t,
}: {
  currentPathname: string;
  item: WorkspaceBootstrapAppBarCategoryItem;
  onClose: () => void;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const Icon = workspaceAppIconForKey(item.icon_key);
  const title = t(`shell:apps.${item.app_id}`, {
    defaultValue: item.title,
  });
  const link = resolveAppLink(item.app_id as WorkspaceAppId);
  return (
    <LauncherLink
      active={isLauncherPathActive({ currentPathname, link })}
      comingSoon={item.coming_soon}
      icon={Icon}
      onClose={onClose}
      title={title}
      to={link}
      t={t}
    />
  );
}

function LauncherLink({
  active,
  comingSoon = false,
  icon: Icon,
  onClose,
  title,
  to,
  t,
}: {
  active: boolean;
  comingSoon?: boolean | null;
  icon: AppBarWorkspaceItem['icon'];
  onClose: () => void;
  title: string;
  to: string;
  t: AppBarTranslator;
}) {
  return (
    <Link
      aria-label={t('shell:appLauncher.openApp', { title })}
      className={cn(
        'group/app relative flex h-24 min-w-0 flex-col items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-center text-app-ink transition-colors hover:border-app-border hover:bg-app-surface-hover',
        active
          ? 'border-app-accent/35 bg-app-bg text-app-accent'
          : 'border-transparent',
        comingSoon && 'opacity-70',
      )}
      onClick={onClose}
      role="menuitem"
      to={to}
    >
      <span
        className={cn(
          'flex size-9 shrink-0 items-center justify-center rounded-lg border transition-colors',
          active
            ? 'border-app-accent/30 bg-app-accent/10 text-app-accent'
            : 'border-app-border bg-app-bg text-app-ink/55 group-hover/app:text-app-ink',
        )}
      >
        <Icon size={20} />
      </span>
      <span className="app-text-caption line-clamp-2 max-w-full font-medium leading-snug">
        {title}
      </span>
      {active ? (
        <Check size={15} className="absolute right-1.5 top-1.5 shrink-0" />
      ) : null}
      {comingSoon ? (
        <span className="app-text-micro absolute right-1 top-1 rounded border border-app-border bg-app-bg px-1 text-app-ink/55">
          {t('shell:sidebar.comingSoon')}
        </span>
      ) : null}
    </Link>
  );
}

function LauncherEditorButton({
  onOpenEditor,
  t,
}: {
  onOpenEditor: () => void;
  t: AppBarTranslator;
}) {
  return (
    <button
      className="app-text-body-sm flex w-full items-center justify-center gap-2 rounded-lg border border-app-border bg-app-bg px-3 py-2 font-medium text-app-ink transition-colors hover:border-app-accent/40 hover:bg-app-surface-hover"
      onClick={onOpenEditor}
      type="button"
    >
      <SlidersHorizontal size={16} className="text-app-ink/55" />
      <span>{t('shell:appBarEditor.open')}</span>
    </button>
  );
}

function EmptyLauncherMessage({ children }: { children: ReactNode }) {
  return (
    <div className="app-text-body-sm rounded-lg border border-dashed border-app-border bg-app-bg px-3 py-5 text-center text-app-ink/55">
      {children}
    </div>
  );
}

function isCategoryActive({
  category,
  currentPathname,
  resolveAppLink,
}: {
  category: WorkspaceBootstrapAppBarCategory;
  currentPathname: string;
  resolveAppLink: AppBarAppLinkResolver;
}) {
  return category.items.some((item) =>
    isLauncherPathActive({
      currentPathname,
      link: resolveAppLink(item.app_id as WorkspaceAppId),
    }),
  );
}

function findActiveCategoryItem({
  category,
  currentPathname,
  resolveAppLink,
}: {
  category: WorkspaceBootstrapAppBarCategory;
  currentPathname: string;
  resolveAppLink: AppBarAppLinkResolver;
}) {
  return (
    category.items.find((item) =>
      isLauncherPathActive({
        currentPathname,
        link: resolveAppLink(item.app_id as WorkspaceAppId),
      }),
    ) ?? null
  );
}

function isLauncherPathActive({
  currentPathname,
  link,
}: {
  currentPathname: string;
  link: string;
}): boolean {
  const pathname = link.split(/[?#]/)[0] || '/';
  return (
    currentPathname === pathname || currentPathname.startsWith(`${pathname}/`)
  );
}
