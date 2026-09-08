import { getAppRoutePattern } from '@open-work-hub/contracts/app-routes';
import { Bot, FolderOpen, Search } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const filesManifest: AppModuleManifest = {
  appBarItem: { id: 'files', title: 'files', icon: FolderOpen },
  contract: {
    owner: 'files-platform',
    permissions: [],
    apiDomain: 'files',
    aiCapabilities: ['files.grounded_chat', 'files.rag_query_rewrite'],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/files/api/files-api.spec.ts',
      'apps/web/src/app-modules/files/manifest.spec.ts',
      'apps/web/src/app-modules/files/routes.spec.tsx',
      'apps/web/src/app-modules/files/sidebar.spec.tsx',
      'apps/web/src/app-modules/files/views/FilesChatView.spec.tsx',
      'apps/web/src/app-modules/files/views/FilesRagSourcesArtifact.spec.tsx',
      'apps/web/src/app-modules/files/views/FileManagerWorkflow.spec.ts',
      'apps/web/src/app-modules/files/views/FileSearchView.spec.tsx',
      'apps/web/src/app-modules/files/views/file-search-view-model.spec.ts',
      'apps/web/src/app-modules/files/views/useFileSearchController.spec.ts',
      'apps/api/tests/test_file_manager.py',
      'apps/api/tests/test_files_search.py',
    ],
  },
  defaultActiveNavItemId: 'files-all',
  navItems: [
    {
      id: 'files-all',
      title: 'files-all',
      icon: FolderOpen,
      category: 'Drive',
      appId: 'files',
    },
    {
      id: 'files-search',
      title: 'files-search',
      icon: Search,
      category: 'Drive',
      appId: 'files',
      pathSuffix: '?view=search',
    },
    {
      id: 'files-chat',
      title: 'files-chat',
      icon: Bot,
      category: 'Drive',
      appId: 'files',
      pathSuffix: '/chat',
    },
  ],
  appRoutePaths: [
    getAppRoutePattern('files.root'),
    getAppRoutePattern('files.chat'),
  ],
};
