import { retrievalSearchManifest } from './manifest';
import { retrievalSearchWorkspaceRoutes } from './routes';

export { retrievalSearchManifest } from './manifest';
export {
  retrievalSearchElement,
  retrievalSearchWorkspaceRoutes,
} from './routes';

export const retrievalSearchModule = {
  manifest: retrievalSearchManifest,
  workspaceRoutes: retrievalSearchWorkspaceRoutes,
} as const;
