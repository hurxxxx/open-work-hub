import type {
  AppSidebarConfig,
  AppSidebarRenderContext,
} from '@/src/app/shell/sidebar-types';
import { learningSidebarConfig } from '@/src/app-modules/learning';

function getBusinessFeatureSidebarConfig(
  activeFeatureAppId?: string | null,
): AppSidebarConfig | null {
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
    return undefined;
  },
};
