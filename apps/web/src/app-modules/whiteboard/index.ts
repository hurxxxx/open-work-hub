import { whiteboardManifest } from './manifest';
import { whiteboardAppRoutes, whiteboardGlobalRoutes } from './routes';
import { whiteboardSidebarConfig } from './sidebar';

export {
  createWhiteboard,
  listWhiteboardHub,
  type WhiteboardHubItem,
} from './api/whiteboard-api';
export {
  whiteboardAppRoutes,
  whiteboardGlobalRoutes,
  whiteboardToolElement,
} from './routes';
export { whiteboardSidebarConfig } from './sidebar';
export { whiteboardManifest };

export const whiteboardModule = {
  globalRoutes: whiteboardGlobalRoutes,
  manifest: whiteboardManifest,
  sidebarConfig: whiteboardSidebarConfig,
  appRoutes: whiteboardAppRoutes,
} as const;
