import { Presentation } from 'lucide-react';

import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';
import { createPptAssistantRouteElements } from './routes';

export const pptAssistantManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'ppt-assistant',
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: 'ppt_generator',
    workspaceApiPrefixes: ['/api/v1/ppt-generator'],
    aiCapabilities: ['ppt_generate'],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/ppt-assistant/ppt-assistant-paths.spec.ts',
      'apps/api/tests/test_ppt_generator.py',
    ],
  },
  surfaces: { aiToolEntry: true },
});

const { historyElement, toolElement } = createPptAssistantRouteElements(
  pptAssistantManifest.moduleId,
);

export const pptAssistantModule = defineFeatureModuleRegistration({
  manifest: pptAssistantManifest,
  shell: {
    navItem: {
      id: pptAssistantManifest.moduleId,
      title: pptAssistantManifest.moduleId,
      icon: Presentation,
      category: 'Business AI',
    },
    tool: { element: toolElement, subSidebar: 'auto' },
    workspaceRoutes: [
      {
        element: historyElement,
        pathSuffix: '/history',
        subSidebar: 'auto',
      },
      {
        element: toolElement,
        pathSuffix: '/jobs/:jobId',
        subSidebar: 'auto',
      },
    ],
  },
});
