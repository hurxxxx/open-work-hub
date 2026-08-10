import { FileSearch } from 'lucide-react';

import {
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from '@/src/app/shell/feature-module-registry';
import { patentPriorArtElement } from './routes';

export const patentPriorArtManifest = defineFeatureModule({
  moduleKind: 'feature',
  moduleId: 'patent-prior-art',
  surfaces: { aiToolEntry: true },
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: 'patent_prior_art',
    resourceScope: 'workspace',
    workspaceApiPrefixes: ['/api/v1/patent-prior-art'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/api/tests/test_patent_prior_art.py',
      'apps/api/tests/test_patent_prior_art_pipeline.py',
      'apps/api/tests/test_patent_prior_art_scaffold.py',
      'apps/web/src/app-modules/patent-prior-art/api/patent-prior-art-api.spec.ts',
      'apps/web/src/app-modules/patent-prior-art/components/PlanChipEditor.spec.tsx',
      'apps/web/src/app-modules/patent-prior-art/controller/job-poll-coordinator.spec.ts',
      'apps/web/src/app-modules/patent-prior-art/controller/usePatentPriorArtController.spec.ts',
      'apps/web/src/app-modules/patent-prior-art/manifest.spec.ts',
      'apps/web/src/app-modules/patent-prior-art/model/patent-prior-art-view-model.spec.ts',
      'apps/worker/tests/apps/patent_prior_art/test_task.py',
    ],
  },
});

export const patentPriorArtModule = defineFeatureModuleRegistration({
  manifest: patentPriorArtManifest,
  shell: {
    navItem: {
      id: 'patent-prior-art',
      title: 'patent-prior-art',
      icon: FileSearch,
      category: 'Patent',
    },
    tool: { element: patentPriorArtElement, subSidebar: 'hidden' },
  },
});
