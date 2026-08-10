import { describe, expect, it } from 'vitest';

import { HEALTH_CHECKUP_ROUTE, managementTasksManifest } from './manifest';

describe('management tasks manifest', () => {
  it('declares a company-resource workspace app contract', () => {
    expect(managementTasksManifest.contract).toMatchObject({
      apiDomain: 'management_tasks',
      permissions: [],
      resourceScope: 'company',
      workspaceApiPrefixes: ['/api/v1/management-tasks'],
    });
  });

  it('publishes only the canonical workspace route', () => {
    expect(managementTasksManifest.workspaceRoutePaths).toEqual([
      HEALTH_CHECKUP_ROUTE,
    ]);
    expect(managementTasksManifest.globalRoutePaths).toBeUndefined();
    expect(
      managementTasksManifest.surfaces?.launcher?.globalPath,
    ).toBeUndefined();
  });

  it('records the app-owned writes and focused test seams', () => {
    expect(managementTasksManifest.contract.writeAuditActions).toEqual([
      'health_checkup.prior_exam.upload',
      'health_checkup.determination.refresh',
      'health_checkup.settings.update',
    ]);
    expect(managementTasksManifest.contract.appLocalTests).toContain(
      'apps/web/src/app-modules/management-tasks/api/health-checkup-api.spec.ts',
    );
    expect(managementTasksManifest.contract.appLocalTests).toContain(
      'apps/web/src/app-modules/management-tasks/views/PriorExamUploadResultPanel.spec.tsx',
    );
    expect(managementTasksManifest.contract.appLocalTests).toContain(
      'apps/api/tests/test_management_tasks_scaffold.py',
    );
  });
});
