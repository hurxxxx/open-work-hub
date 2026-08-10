import { Mail } from 'lucide-react';

import { emailAssistantToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const emailAssistantManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'email-assistant',
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

export const emailAssistantModule = defineFeatureModuleRegistration({
  manifest: emailAssistantManifest,
  shell: {
    navItem: {
      id: 'email-assistant',
      title: 'email-assistant',
      icon: Mail,
      category: 'Business AI',
    },
    tool: {
      element: emailAssistantToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
