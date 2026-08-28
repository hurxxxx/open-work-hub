import { whiteboardManifest } from './manifest';
import { whiteboardGlobalRoutes, whiteboardWorkspaceRoutes } from './routes';
import { whiteboardSidebarConfig } from './sidebar';

export { whiteboardManifest };
export {
  whiteboardGlobalRoutes,
  whiteboardToolElement,
  whiteboardWorkspaceRoutes,
} from './routes';
export { whiteboardSidebarConfig } from './sidebar';
export {
  createWhiteboard,
  listWhiteboardHub,
  type WhiteboardHubItem,
} from './api/whiteboard-api';

export const whiteboardModule = {
  globalRoutes: whiteboardGlobalRoutes,
  manifest: whiteboardManifest,
  sidebarConfig: whiteboardSidebarConfig,
  workspaceRoutes: whiteboardWorkspaceRoutes,
} as const;
