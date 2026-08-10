import { createElement } from 'react';
import { FileBarChart } from 'lucide-react';

import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';
import { ComingSoonView } from '@/src/app/shell/tool-views/ComingSoonView';

const patentReportNavItem = {
  id: 'patent-report',
  title: 'patent-report',
  icon: FileBarChart,
  category: 'Patent',
  comingSoon: true,
} as const;

export const patentReportManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'patent-report',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'patent',
    workspaceApiPrefixes: ['/api/v1/patent'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_patent.py'],
  },
  surfaces: { aiToolEntry: true },
});

export const patentReportModule = defineFeatureModuleRegistration({
  manifest: patentReportManifest,
  shell: {
    navItem: patentReportNavItem,
    tool: {
      element: createElement(ComingSoonView, { item: patentReportNavItem }),
      subSidebar: 'hidden',
    },
  },
});
