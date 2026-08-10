import { ClipboardCheck } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const patentAutomationManifest: AppModuleManifest = {
  appBarItem: {
    id: 'patent-automation',
    title: 'patent-automation',
    icon: ClipboardCheck,
  },
  contract: {
    owner: 'patent-team',
    permissions: [],
    apiDomain: 'patent_automation',
    workspaceApiPrefixes: ['/api/v1/patent-automation'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_patent_automation.py'],
  },
  defaultActiveNavItemId: 'patent-automation',
  navItems: [
    {
      id: 'patent-automation',
      title: 'patent-automation',
      icon: ClipboardCheck,
      category: 'Patent',
      appId: 'patent-automation',
      description: 'patent-automation',
    },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/patent-automation'],
};
