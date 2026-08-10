import { Languages } from 'lucide-react';

import { documentTranslateToolElement } from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

export const documentTranslateManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'document-translate',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'document_translate',
    workspaceApiPrefixes: ['/api/v1/document-translate'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_document_translate.py'],
  },
  surfaces: { aiToolEntry: true },
});

export const documentTranslateModule = defineFeatureModuleRegistration({
  manifest: documentTranslateManifest,
  shell: {
    navItem: {
      id: 'translate',
      title: 'translate',
      icon: Languages,
      category: 'Business AI',
    },
    tool: {
      element: documentTranslateToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
