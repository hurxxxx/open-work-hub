import { aiSidebarConfig } from '@/src/app-modules/ai/sidebar';
import { docsSidebarConfig } from '@/src/app-modules/docs/sidebar';
import { learningSidebarConfig } from '@/src/app-modules/learning/sidebar';
import { meetingSidebarConfig } from '@/src/app-modules/meeting/sidebar';
import { plannerSidebarConfig } from '@/src/app-modules/planner/sidebar';
import { pmsSidebarConfig } from '@/src/app-modules/pms/sidebar/config';
import { whiteboardSidebarConfig } from '@/src/app-modules/whiteboard/sidebar';
import type { AppModuleId } from './navigation-types';
import type { AppSidebarConfig } from './sidebar-types';

const SIDEBAR_CONFIGS: Partial<Record<AppModuleId, AppSidebarConfig>> = {
  ai: aiSidebarConfig,
  docs: docsSidebarConfig,
  learning: learningSidebarConfig,
  meeting: meetingSidebarConfig,
  planner: plannerSidebarConfig,
  pms: pmsSidebarConfig,
  whiteboard: whiteboardSidebarConfig,
};

export function getAppSidebarConfig(
  appId: string,
): AppSidebarConfig | null {
  return SIDEBAR_CONFIGS[appId as AppModuleId] ?? null;
}
