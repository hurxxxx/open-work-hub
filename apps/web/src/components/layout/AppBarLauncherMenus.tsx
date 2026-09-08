import { Check, Search, SlidersHorizontal, Star } from 'lucide-react';
import {
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@/src/lib/utils';
import { appIconForKey } from '@/src/platform/apps/app-icons';
import type { ShellAppId } from '@/src/platform/apps/app-links';
import type {
  BootstrapAppBarCategory,
  BootstrapAppBarCategoryItem,
} from '@/src/platform/apps/apps-api';
import { AppBarEditor } from './AppBarEditor';
import {
  AppBarRailActiveIndicator,
  AppBarRailTooltip,
  appBarRailControlClassName,
} from './AppBarIconLink';
import {
  type AppBarAppContextLabelResolver,
  type AppBarAppLabelResolver,
  type AppBarAppLinkResolver,
  type AppBarLaunchItem,
  type AppBarTranslator,
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
  currentCompanyLabel,
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
  resolveAppContextLabel,
  resolveAppLabel,
  t,
}: {
  appBarEditorOpen: boolean;
  appBarLayoutError: string | null;
  appBarLayoutSaving: boolean;
  categoryMenuId: string | null;
  currentPathname: string;
  currentCompanyLabel: string | null;
  draftItems: AppBarLaunchItem[];
  draftPinnedAppIds: ShellAppId[];
  favoritesActive: boolean;
  favoritesOpen: boolean;
  launcherCategories: BootstrapAppBarCategory[];
  menuRef: RefObject<HTMLDivElement | null>;
  onCloseEditor: () => void;
  onCloseLauncherMenus: () => void;
  onMovePinnedApp: (appId: ShellAppId, direction: -1 | 1) => void;
  onOpenEditor: () => void;
  onResetDraft: () => void;
  onSaveLayout: () => void;
  onToggleCategoryMenu: (categoryId: string) => void;
  onToggleFavorites: () => void;
  onTogglePinnedApp: (appId: ShellAppId, checked: boolean) => void;
  pinnedEligibleAppIds: ReadonlySet<ShellAppId>;
  pinnedItems: AppBarLaunchItem[];
  resolveAppLink: AppBarAppLinkResolver;
  resolveAppContextLabel: AppBarAppContextLabelResolver;
  resolveAppLabel: AppBarAppLabelResolver;
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

  useEffect(() => {
    if (!favoritesOpen && !categoryMenuId) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') {
        return;
      }
      const trigger = menuRef.current?.querySelector<HTMLButtonElement>(
        'button[aria-haspopup="menu"][aria-expanded="true"]',
      );
      event.preventDefault();
      event.stopPropagation();
      onCloseLauncherMenus();
      window.requestAnimationFrame(() => trigger?.focus());
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [categoryMenuId, favoritesOpen, menuRef, onCloseLauncherMenus]);

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
          currentCompanyLabel={currentCompanyLabel}
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
                  resolveAppContextLabel={resolveAppContextLabel}
                  resolveAppLabel={resolveAppLabel}
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
            currentCompanyLabel={currentCompanyLabel}
            currentPathname={currentPathname}
            key={category.id}
            onClose={onCloseLauncherMenus}
            onToggle={() => onToggleCategoryMenu(category.id)}
            open={categoryMenuId === category.id}
            resolveAppLink={resolveAppLink}
            resolveAppContextLabel={resolveAppContextLabel}
            resolveAppLabel={resolveAppLabel}
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
                currentCompanyLabel={currentCompanyLabel}
                currentPathname={currentPathname}
                onClose={onCloseLauncherMenus}
                onToggle={() => onToggleCategoryMenu(category.id)}
                open={categoryMenuId === category.id}
                resolveAppLink={resolveAppLink}
                resolveAppContextLabel={resolveAppContextLabel}
                resolveAppLabel={resolveAppLabel}
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
  currentCompanyLabel,
  currentPathname,
  onClose,
  onToggle,
  open,
  resolveAppContextLabel,
  resolveAppLabel,
  resolveAppLink,
  t,
}: {
  active: boolean;
  activeItem: BootstrapAppBarCategoryItem | null;
  category: BootstrapAppBarCategory;
  currentCompanyLabel: string | null;
  currentPathname: string;
  onClose: () => void;
  onToggle: () => void;
  open: boolean;
  resolveAppContextLabel: AppBarAppContextLabelResolver;
  resolveAppLabel: AppBarAppLabelResolver;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const Icon = appIconForKey(activeItem?.icon_key ?? category.icon_key);
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
          currentCompanyLabel={category.contextLabel ?? currentCompanyLabel}
          iconKey={category.icon_key}
          title={title}
        >
          <CategoryItemSearch
            category={category}
            currentPathname={currentPathname}
            columnCount={columnCount}
            onClose={onClose}
            resolveAppContextLabel={resolveAppContextLabel}
            resolveAppLabel={resolveAppLabel}
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
  resolveAppContextLabel,
  resolveAppLabel,
  resolveAppLink,
  t,
}: {
  category: BootstrapAppBarCategory;
  columnCount: LauncherGridColumnCount;
  currentPathname: string;
  onClose: () => void;
  resolveAppContextLabel: AppBarAppContextLabelResolver;
  resolveAppLabel: AppBarAppLabelResolver;
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
              resolveAppContextLabel={resolveAppContextLabel}
              resolveAppLabel={resolveAppLabel}
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
  currentCompanyLabel,
  iconKey,
  title,
}: {
  children: ReactNode;
  columnCount?: LauncherGridColumnCount;
  currentCompanyLabel: string | null;
  iconKey: string;
  title: string;
}) {
  const Icon = appIconForKey(iconKey);
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
          {currentCompanyLabel ? (
            <div className="app-text-caption truncate text-app-ink/55">
              {currentCompanyLabel}
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
  resolveAppContextLabel,
  resolveAppLabel,
  resolveAppLink,
  t,
}: {
  currentPathname: string;
  item: AppBarLaunchItem;
  onClose: () => void;
  resolveAppContextLabel: AppBarAppContextLabelResolver;
  resolveAppLabel: AppBarAppLabelResolver;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const link = resolveAppLink(item.id);
  return (
    <LauncherLink
      accessibleLabel={resolveAppLabel(item.id, item.title)}
      active={isLauncherPathActive({ currentPathname, link })}
      icon={item.icon}
      onClose={onClose}
      scopeLabel={resolveAppContextLabel(item.id)}
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
  resolveAppContextLabel,
  resolveAppLabel,
  resolveAppLink,
  t,
}: {
  currentPathname: string;
  item: BootstrapAppBarCategoryItem;
  onClose: () => void;
  resolveAppContextLabel: AppBarAppContextLabelResolver;
  resolveAppLabel: AppBarAppLabelResolver;
  resolveAppLink: AppBarAppLinkResolver;
  t: AppBarTranslator;
}) {
  const Icon = appIconForKey(item.icon_key);
  const title = t(`shell:apps.${item.app_id}`, {
    defaultValue: item.title,
  });
  const appId = item.app_id as ShellAppId;
  const link = resolveAppLink(appId);
  return (
    <LauncherLink
      accessibleLabel={resolveAppLabel(appId, title)}
      active={isLauncherPathActive({ currentPathname, link })}
      comingSoon={item.coming_soon}
      icon={Icon}
      onClose={onClose}
      scopeLabel={resolveAppContextLabel(appId)}
      title={title}
      to={link}
      t={t}
    />
  );
}

function LauncherLink({
  accessibleLabel,
  active,
  comingSoon = false,
  icon: Icon,
  onClose,
  scopeLabel,
  title,
  to,
  t,
}: {
  accessibleLabel: string;
  active: boolean;
  comingSoon?: boolean | null;
  icon: AppBarLaunchItem['icon'];
  onClose: () => void;
  scopeLabel?: string | null;
  title: string;
  to: string;
  t: AppBarTranslator;
}) {
  return (
    <Link
      aria-label={accessibleLabel}
      className={cn(
        'group/app relative flex h-28 min-w-0 flex-col items-center justify-center gap-1 rounded-lg border px-2 py-2 text-center text-app-ink transition-colors hover:border-app-border hover:bg-app-surface-hover',
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
      {scopeLabel ? (
        <span className="app-text-micro max-w-full truncate rounded-full bg-app-surface px-1.5 py-0.5 text-app-ink/50">
          {scopeLabel}
        </span>
      ) : null}
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
  category: BootstrapAppBarCategory;
  currentPathname: string;
  resolveAppLink: AppBarAppLinkResolver;
}) {
  return category.items.some((item) =>
    isLauncherPathActive({
      currentPathname,
      link: resolveAppLink(item.app_id as ShellAppId),
    }),
  );
}

function findActiveCategoryItem({
  category,
  currentPathname,
  resolveAppLink,
}: {
  category: BootstrapAppBarCategory;
  currentPathname: string;
  resolveAppLink: AppBarAppLinkResolver;
}) {
  return (
    category.items.find((item) =>
      isLauncherPathActive({
        currentPathname,
        link: resolveAppLink(item.app_id as ShellAppId),
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
