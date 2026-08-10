import { GraduationCap } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const learningManifest: AppModuleManifest = {
  appBarItem: { id: 'learning', title: 'learning', icon: GraduationCap },
  contract: {
    owner: 'learning-platform',
    permissions: [],
    apiDomain: 'learning_notes',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/learning/model/manifest.spec.ts',
      'apps/api/tests/test_learning_notes.py',
    ],
  },
  defaultActiveNavItemId: 'learning-home',
  navItems: [
    { id: 'learning-home', title: 'learning-home', icon: GraduationCap, category: 'Courses', appId: 'learning', description: 'learning-home' },
  ],
  workspaceRoutePaths: [
    '/w/:workspaceSlug/learning',
    '/w/:workspaceSlug/learning/:courseSlug',
    '/w/:workspaceSlug/learning/:courseSlug/:lessonSlug',
  ],
};
