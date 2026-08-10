import { FileText } from 'lucide-react';

import { draftingToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const draftingManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'drafting',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'writing_assistant',
    workspaceApiPrefixes: ['/api/v1/writing-assistant'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/ai/views/writing-assistant-parts.spec.tsx',
      'apps/api/tests/test_writing_assistant_schemas.py',
    ],
  },
  surfaces: { aiToolEntry: true },
});

export const draftingModule = defineFeatureModuleRegistration({
  manifest: draftingManifest,
  shell: {
    navItem: {
      id: 'drafting',
      title: 'drafting',
      icon: FileText,
      category: 'Business AI',
    },
    tool: {
      element: draftingToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
