import { Gem } from 'lucide-react';

import { imdsMineralsToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const imdsMineralsManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'imds-minerals',
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: 'imds_minerals',
    workspaceApiPrefixes: ['/api/v1/imds-minerals'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_imds_minerals.py'],
  },
});

export const imdsMineralsModule = defineFeatureModuleRegistration({
  manifest: imdsMineralsManifest,
  shell: {
    navItem: {
      id: 'imds-minerals',
      title: 'imds-minerals',
      icon: Gem,
      category: 'Business AI',
    },
    tool: { element: imdsMineralsToolElement, subSidebar: 'hidden' },
  },
});
