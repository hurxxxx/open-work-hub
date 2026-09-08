import { FileUploadProvider } from './file-upload-provider';
import { filesManifest } from './manifest';
import { filesAppRoutes } from './routes';
import { filesSidebarConfig } from './sidebar';

export {
  filesAppRoutes,
  filesManifest,
  filesSidebarConfig,
  FileUploadProvider,
};

export const filesModule = {
  manifest: filesManifest,
  shellProviders: [FileUploadProvider],
  sidebarConfig: filesSidebarConfig,
  appRoutes: filesAppRoutes,
} as const;
