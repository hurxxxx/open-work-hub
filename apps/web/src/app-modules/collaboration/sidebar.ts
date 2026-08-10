import type { AppSidebarConfig } from '@/src/app/shell/sidebar-types';
import { diagramsSidebarConfig } from '@/src/app-modules/diagrams';
import { docsSidebarConfig } from '@/src/app-modules/docs';
import { filesSidebarConfig } from '@/src/app-modules/files';
import { meetingSidebarConfig } from '@/src/app-modules/meeting';
import { plannerSidebarConfig } from '@/src/app-modules/planner';
import { pmsSidebarConfig } from '@/src/app-modules/pms';
import { whiteboardSidebarConfig } from '@/src/app-modules/whiteboard';

function getCollaborationFeatureSidebarConfig(
  activeFeatureAppId?: string | null,
): AppSidebarConfig | null {
  switch (activeFeatureAppId) {
    case 'diagrams':
      return diagramsSidebarConfig;
    case 'docs':
      return docsSidebarConfig;
    case 'files':
      return filesSidebarConfig;
    case 'meeting':
      return meetingSidebarConfig;
    case 'planner':
      return plannerSidebarConfig;
    case 'pms':
      return pmsSidebarConfig;
    case 'whiteboard':
      return whiteboardSidebarConfig;
    default:
      return null;
  }
}

export const collaborationSidebarConfig: AppSidebarConfig = {
  createActions: (context) =>
    getCollaborationFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.createActions?.(context) ?? [],
  extendCategories: (categories, context) => {
    return (
      getCollaborationFeatureSidebarConfig(
        context.activeFeatureAppId,
      )?.extendCategories?.(categories, context) ?? categories
    );
  },
  beforeCategories: (context) =>
    getCollaborationFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.beforeCategories?.(context),
  afterCategories: (context) =>
    getCollaborationFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.afterCategories?.(context),
  renderCategory: (category, context) => {
    return getCollaborationFeatureSidebarConfig(
      context.activeFeatureAppId,
    )?.renderCategory?.(category, context);
  },
};
