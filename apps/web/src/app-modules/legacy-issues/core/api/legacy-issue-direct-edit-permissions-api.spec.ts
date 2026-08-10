import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  fetchLegacyIssueModuleDirectEditors,
  grantLegacyIssueModuleDirectEditor,
  revokeLegacyIssueModuleDirectEditor,
} from './legacy-issue-direct-edit-permissions-api';

const apiFetchJson = vi.fn();

vi.mock('@/src/platform/api/client', () => ({
  apiFetchJson: (...args: unknown[]) => apiFetchJson(...args),
}));

describe('legacy issue direct edit permissions api', () => {
  beforeEach(() => {
    apiFetchJson.mockReset();
    apiFetchJson.mockResolvedValue({ items: [] });
  });

  it('loads grants for an encoded workspace and module', async () => {
    await fetchLegacyIssueModuleDirectEditors({
      moduleKey: 'electrical-control-sw',
      token: 'token',
      workspaceSlug: 'workspace / one',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/workspace%20%2F%20one/legacy-issues/module-direct-editors?module_key=electrical-control-sw',
      'token',
    );
  });

  it('loads all module grants without a module query', async () => {
    await fetchLegacyIssueModuleDirectEditors({
      token: 'token',
      workspaceSlug: 'workspace',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/workspace/legacy-issues/module-direct-editors',
      'token',
    );
  });

  it('grants and revokes one user idempotently', async () => {
    await grantLegacyIssueModuleDirectEditor({
      moduleKey: 'aircon',
      token: 'token',
      userId: 'user / one',
      workspaceSlug: 'workspace',
    });
    await revokeLegacyIssueModuleDirectEditor({
      moduleKey: 'aircon',
      token: 'token',
      userId: 'user / one',
      workspaceSlug: 'workspace',
    });

    const path =
      '/api/v1/workspaces/workspace/legacy-issues/module-direct-editors/aircon/users/user%20%2F%20one';
    expect(apiFetchJson).toHaveBeenNthCalledWith(1, path, 'token', {
      method: 'PUT',
    });
    expect(apiFetchJson).toHaveBeenNthCalledWith(2, path, 'token', {
      method: 'DELETE',
    });
  });
});
