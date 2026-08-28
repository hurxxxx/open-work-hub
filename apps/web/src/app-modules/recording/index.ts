import { recordingManifest } from './manifest';
import { recordingWorkspaceRoutes } from './routes';
import { recordingShellNavResolver } from './shell-nav';

export {
  recordingManifest,
  recordingShellNavResolver,
  recordingWorkspaceRoutes,
};

export const recordingModule = {
  manifest: recordingManifest,
  shellNavResolver: recordingShellNavResolver,
  workspaceRoutes: recordingWorkspaceRoutes,
} as const;
