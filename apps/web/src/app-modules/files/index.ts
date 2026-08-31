import { FileUploadProvider } from './file-upload-provider';
import { filesManifest } from './manifest';
import { filesWorkspaceRoutes } from './routes';
import { filesSidebarConfig } from './sidebar';

export {
  FileUploadProvider,
  filesManifest,
  filesSidebarConfig,
  filesWorkspaceRoutes,
};

export const filesModule = {
  manifest: filesManifest,
  shellProviders: [FileUploadProvider],
  sidebarConfig: filesSidebarConfig,
  workspaceRoutes: filesWorkspaceRoutes,
} as const;
