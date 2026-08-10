import { Gavel } from 'lucide-react';

import { patentComposeToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const patentComposeManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'patent-compose',
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

export const patentComposeModule = defineFeatureModuleRegistration({
  manifest: patentComposeManifest,
  shell: {
    navItem: {
      id: 'patent-interpret',
      title: 'patent-interpret',
      icon: Gavel,
      category: 'Patent',
    },
    tool: {
      element: patentComposeToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
