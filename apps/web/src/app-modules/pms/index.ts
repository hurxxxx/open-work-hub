import { pmsManifest } from './manifest';
import { pmsAppRoutes } from './routes';
import { pmsShellNavResolver } from './shell-nav';
import { pmsSidebarConfig } from './sidebar/config';

export { getPmsHelpGuideSrc, pmsHelpGuideRegistration } from './help-guide';
export { pmsAppRoutes, pmsToolElement } from './routes';
export { pmsShellNavResolver } from './shell-nav';
export { pmsSidebarConfig } from './sidebar/config';
export { PmsSidebarSpaces } from './sidebar/PmsSidebarSpaces';
export {
  FloatingPmsWidget,
  useFloatingPmsAssignedCount,
  useFloatingPmsAssignedSummary,
  type FloatingPmsWidgetOpenRequest,
} from './views/FloatingPmsWidget';
export { pmsManifest };

export const pmsModule = {
  manifest: pmsManifest,
  shellNavResolver: pmsShellNavResolver,
  sidebarConfig: pmsSidebarConfig,
  appRoutes: pmsAppRoutes,
} as const;
