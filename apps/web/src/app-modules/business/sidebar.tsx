import { Link, useLocation } from 'react-router-dom';
import { BookOpen, FilePlus2, History, LayoutGrid } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  AppSidebarConfig,
  AppSidebarRenderContext,
} from '@/src/app/shell/sidebar-types';
import { learningSidebarConfig } from '@/src/app-modules/learning';
import { legacyIssuesSidebarConfig } from '@/src/app-modules/legacy-issues';
import { cn } from '@/src/lib/utils';
import { buildWorkspaceAppPath } from '@/src/platform/workspaces/workspace-utils';

function PptAssistantSidebarSection({
  context,
}: {
  context: AppSidebarRenderContext;
}) {
  const { t } = useTranslation('apps');
  const location = useLocation();
  const workspaceSlug = context.currentWorkspaceSlug;
  if (!workspaceSlug) return null;

  const newPath = buildWorkspaceAppPath(workspaceSlug, 'ppt-assistant');
  const historyPath = buildWorkspaceAppPath(
    workspaceSlug,
    'ppt-assistant',
    '/history',
  );
  const templatesPath = `${newPath}?tab=templates`;
  const guidePath = `${newPath}?tab=guide`;
  const currentPath = context.currentPathname;
  const activeTab = new URLSearchParams(location.search).get('tab');
  const newActive = currentPath === newPath && !activeTab;
  const templatesActive = currentPath === newPath && activeTab === 'templates';
  const guideActive = currentPath === newPath && activeTab === 'guide';
  const historyActive =
    currentPath === historyPath ||
    currentPath.includes('/ppt-assistant/jobs/') ||
    (currentPath === newPath && activeTab === 'materials');

  return (
    <div className="space-y-1">
      <div className="sidebar-section-label px-3 py-1 text-app-ink/55">
        {t('ai.pptGenerator.sidebar.title')}
      </div>
      <Link
        to={newPath}
        onClick={context.onNavigate}
        className={cn(
          'sidebar-submenu-item ml-1',
          newActive && 'sidebar-submenu-item-active',
        )}
      >
        <FilePlus2 size={16} className="text-app-ink/55 dark:text-app-ink/65" />
        <span className="sidebar-submenu-label">
          {t('ai.pptGenerator.sidebar.new')}
        </span>
      </Link>
      <Link
        to={templatesPath}
        onClick={context.onNavigate}
        className={cn(
          'sidebar-submenu-item ml-1',
          templatesActive && 'sidebar-submenu-item-active',
        )}
      >
        <LayoutGrid
          size={16}
          className="text-app-ink/55 dark:text-app-ink/65"
        />
        <span className="sidebar-submenu-label">
          {t('ai.pptGenerator.sidebar.templates')}
        </span>
      </Link>
      <Link
        to={historyPath}
        onClick={context.onNavigate}
        className={cn(
          'sidebar-submenu-item ml-1',
          historyActive && 'sidebar-submenu-item-active',
        )}
      >
        <History size={16} className="text-app-ink/55 dark:text-app-ink/65" />
        <span className="sidebar-submenu-label">
          {t('ai.pptGenerator.sidebar.history')}
        </span>
      </Link>
      <Link
        to={guidePath}
        onClick={context.onNavigate}
        className={cn(
          'sidebar-submenu-item ml-1',
          guideActive && 'sidebar-submenu-item-active',
        )}
      >
        <BookOpen size={16} className="text-app-ink/55 dark:text-app-ink/65" />
        <span className="sidebar-submenu-label">
          {t('ai.pptGenerator.sidebar.guide')}
        </span>
      </Link>
    </div>
  );
}

function isLegacyIssuesFeature(activeFeatureAppId?: string | null): boolean {
  return activeFeatureAppId === 'legacy-issues';
}

function getBusinessFeatureSidebarConfig(
  activeFeatureAppId?: string | null,
): AppSidebarConfig | null {
  if (isLegacyIssuesFeature(activeFeatureAppId)) {
    return legacyIssuesSidebarConfig;
  }
  if (activeFeatureAppId === 'learning') {
    return learningSidebarConfig;
  }
  return null;
}

export const businessSidebarConfig: AppSidebarConfig = {
  createActions: (context) =>
    getBusinessFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.createActions?.(context) ?? [],
  extendCategories: (categories, context) =>
    getBusinessFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.extendCategories?.(categories, context) ?? categories,
  beforeCategories: (context) =>
    getBusinessFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.beforeCategories?.(context),
  afterCategories: (context) =>
    getBusinessFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.afterCategories?.(context),
  renderCategory: (category, context) => {
    const featureCategory = getBusinessFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.renderCategory?.(category, context);
    if (featureCategory !== undefined) {
      return featureCategory;
    }
    if (
      context.activeFeatureAppId === 'ppt-assistant' &&
      context.filteredItems.some(
        (item) => item.id === 'ppt-assistant' && item.category === category,
      )
    ) {
      return <PptAssistantSidebarSection context={context} />;
    }
    return undefined;
  },
};
