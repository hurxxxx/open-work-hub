import { managementTasksManifest } from './manifest';
import { managementTasksWorkspaceRoutes } from './routes';

export {
  HEALTH_CHECKUP_ROUTE,
  MANAGEMENT_TASKS_APP_ID,
  managementTasksManifest,
} from './manifest';
export { managementTasksWorkspaceRoutes } from './routes';

export const managementTasksModule = {
  manifest: managementTasksManifest,
  workspaceRoutes: managementTasksWorkspaceRoutes,
} as const;
