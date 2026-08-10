import { Activity } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const MANAGEMENT_TASKS_APP_ID = 'management-tasks';
export const HEALTH_CHECKUP_ROUTE = '/w/:workspaceSlug/management-tasks';

export const managementTasksManifest: AppModuleManifest = {
  appBarItem: {
    id: 'management-tasks',
    title: MANAGEMENT_TASKS_APP_ID,
    icon: Activity,
  },
  contract: {
    owner: 'management-team',
    permissions: [],
    apiDomain: 'management_tasks',
    resourceScope: 'company',
    workspaceApiPrefixes: ['/api/v1/management-tasks'],
    aiCapabilities: [],
    writeAuditActions: [
      'health_checkup.prior_exam.upload',
      'health_checkup.determination.refresh',
      'health_checkup.settings.update',
    ],
    appLocalTests: [
      'apps/api/tests/test_management_tasks_scaffold.py',
      'apps/web/src/app-modules/management-tasks/manifest.spec.ts',
      'apps/web/src/app-modules/management-tasks/routes.spec.tsx',
      'apps/web/src/app-modules/management-tasks/api/health-checkup-api.spec.ts',
      'apps/web/src/app-modules/management-tasks/views/AccessibleMultiSelect.spec.tsx',
      'apps/web/src/app-modules/management-tasks/views/HealthCheckupPagination.spec.tsx',
      'apps/web/src/app-modules/management-tasks/views/HealthCheckupSourceStatusPanel.spec.tsx',
      'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.spec.tsx',
      'apps/web/src/app-modules/management-tasks/views/PriorExamUploadResultPanel.spec.tsx',
      'apps/web/src/app-modules/management-tasks/views/useHealthCheckupController.spec.tsx',
      'apps/api/tests/test_management_tasks_health_checkup.py',
    ],
  },
  defaultActiveNavItemId: 'health-checkup',
  navItems: [
    {
      id: 'health-checkup',
      title: 'health-checkup',
      icon: Activity,
      category: 'nurse',
      appId: MANAGEMENT_TASKS_APP_ID,
      description: 'health-checkup',
    },
  ],
  workspaceRoutePaths: [HEALTH_CHECKUP_ROUTE],
};
