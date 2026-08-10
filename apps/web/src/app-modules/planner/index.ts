import { plannerManifest } from './manifest';
import { plannerGlobalRoutes } from './routes';
import { plannerSidebarConfig } from './sidebar';

export { plannerManifest };
export { plannerGlobalRoutes };
export { plannerSidebarConfig };
export {
  FloatingTodayPlannerWidget,
  useFloatingTodayPlannerCount,
} from './views/FloatingTodayPlannerWidget';

export const plannerModule = {
  globalRoutes: plannerGlobalRoutes,
  manifest: plannerManifest,
  sidebarConfig: plannerSidebarConfig,
} as const;
