import { ImageIcon } from 'lucide-react';

import {
  createImageWizardBackgroundWorkSource,
  imageWizardToolElement,
} from '@/src/app-modules/ai';
import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';

/**
 * Leaf registration for the image generation app.
 *
 * The registry injects the manifest identity into every capability and shell
 * surface so platform composition never needs to repeat this app id.
 */
export const imageWizardManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'image-wizard',
  contract: {
    owner: 'ai-platform',
    permissions: [],
    apiDomain: 'images',
    workspaceApiPrefixes: ['/api/v1/images'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_image_generation_jobs.py',
      'apps/api/tests/test_image_context_refs.py',
    ],
  },
  surfaces: { aiToolEntry: true },
});

export const imageWizardModule = defineFeatureModuleRegistration({
  manifest: imageWizardManifest,
  backgroundWorkSourceFactories: [
    ({ appId }) => createImageWizardBackgroundWorkSource(appId),
  ],
  shell: {
    navItem: {
      id: 'image-wizard',
      title: 'image-wizard',
      icon: ImageIcon,
      category: 'Business AI',
    },
    tool: {
      element: imageWizardToolElement,
      featureGuide: true,
      subSidebar: 'hidden',
    },
  },
});
