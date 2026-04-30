import { aiSidebarConfig } from '@/src/app-modules/ai';
import { docsSidebarConfig } from '@/src/app-modules/docs';
import { learningSidebarConfig } from '@/src/app-modules/learning';
import { meetingSidebarConfig } from '@/src/app-modules/meeting';
import { plannerSidebarConfig } from '@/src/app-modules/planner';
import { pmsSidebarConfig } from '@/src/app-modules/pms';
import type { AppModuleId } from './navigation-types';
import type { AppSidebarConfig } from './sidebar-types';

const SIDEBAR_CONFIGS: Partial<Record<AppModuleId, AppSidebarConfig>> = {
  ai: aiSidebarConfig,
  docs: docsSidebarConfig,
  learning: learningSidebarConfig,
  meeting: meetingSidebarConfig,
  planner: plannerSidebarConfig,
  pms: pmsSidebarConfig,
};

export function getAppSidebarConfig(
  appId: string,
): AppSidebarConfig | null {
  return SIDEBAR_CONFIGS[appId as AppModuleId] ?? null;
}
