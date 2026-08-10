import { AlertTriangle } from 'lucide-react';

import { fmeaCompareToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const fmeaCompareManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'fmea-compare',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'fmea_compare',
    workspaceApiPrefixes: ['/api/v1/fmea-compare'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_platform_adapter_registries.py'],
  },
  surfaces: { aiToolEntry: true },
});

export const fmeaCompareModule = defineFeatureModuleRegistration({
  manifest: fmeaCompareManifest,
  shell: {
    navItem: {
      id: 'fmea-compare',
      title: 'fmea-compare',
      icon: AlertTriangle,
      category: 'Business AI',
    },
    tool: {
      element: fmeaCompareToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
