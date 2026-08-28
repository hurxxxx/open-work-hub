import { pmsManifest } from './manifest';
import { pmsWorkspaceRoutes } from './routes';
import { pmsSidebarConfig } from './sidebar/config';
import { pmsShellNavResolver } from './shell-nav';

export { pmsManifest };
export { pmsHelpGuideRegistration } from './help-guide';
export { pmsToolElement, pmsWorkspaceRoutes } from './routes';
export { pmsSidebarConfig } from './sidebar/config';
export { pmsShellNavResolver } from './shell-nav';
export { PmsSidebarSpaces } from './sidebar/PmsSidebarSpaces';
export {
  FloatingPmsWidget,
  type FloatingPmsWidgetOpenRequest,
  useFloatingPmsAssignedCount,
  useFloatingPmsAssignedSummary,
} from './views/FloatingPmsWidget';

export const pmsModule = {
  manifest: pmsManifest,
  shellNavResolver: pmsShellNavResolver,
  sidebarConfig: pmsSidebarConfig,
  workspaceRoutes: pmsWorkspaceRoutes,
} as const;
