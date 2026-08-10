import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  cancelLegacyIssueDatasetRevision,
  deleteLegacyIssueGridPreference,
  fetchLegacyIssueGridPreference,
  saveLegacyIssueDatasetRecordBatch,
  updateLegacyIssueColumnOrder,
  updateLegacyIssueGridPreference,
} from './legacy-issue-dataset-api';

const apiFetchJson = vi.fn();

vi.mock('@/src/platform/api/client', () => ({
  ApiRequestError: class ApiRequestError extends Error {},
  apiFetchJson: (...args: unknown[]) => apiFetchJson(...args),
  jsonHeaders: { 'Content-Type': 'application/json' },
}));

describe('legacy issue dataset api', () => {
  beforeEach(() => {
    apiFetchJson.mockReset();
    apiFetchJson.mockResolvedValue({});
  });

  it('sends an explicit force flag after an authorized editor confirms draft cancellation', async () => {
    await cancelLegacyIssueDatasetRevision({
      datasetKey: 'common-master',
      force: true,
      revisionId: 'draft / one',
      token: 'token',
      viewKey: 'aircon',
      workspaceSlug: 'workspace / one',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/workspace%20%2F%20one/legacy-issues/datasets/common-master/revisions/draft%20%2F%20one/cancel?view_key=aircon',
      'token',
      {
        body: JSON.stringify({ force: true }),
        method: 'POST',
      },
    );
  });

  it('saves record changes without a shared grid layout', async () => {
    await saveLegacyIssueDatasetRecordBatch({
      creates: [],
      datasetKey: 'common-master',
      revisionId: 'revision-1',
      token: 'token',
      updates: [],
      viewKey: 'aircon',
      workspaceSlug: 'workspace',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/workspace/legacy-issues/datasets/common-master/records/batch?view_key=aircon&revision_id=revision-1',
      'token',
      {
        body: JSON.stringify({
          creates: [],
          release_editing: false,
          updates: [],
        }),
        method: 'PATCH',
      },
    );
  });

  it('saves administrator-hidden columns with the shared column order', async () => {
    await updateLegacyIssueColumnOrder({
      payload: {
        column_order: ['status', 'problem'],
        hidden_column_keys: ['problem'],
      },
      token: 'token',
      viewKey: 'aircon',
      workspaceSlug: 'workspace',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/workspace/legacy-issues/column-orders/aircon',
      'token',
      {
        body: JSON.stringify({
          column_order: ['status', 'problem'],
          hidden_column_keys: ['problem'],
        }),
        method: 'PUT',
      },
    );
  });

  it('loads, saves, and resets a user grid preference in its workspace scope', async () => {
    await fetchLegacyIssueGridPreference({
      gridKey: 'aircon / current',
      gridKind: 'dataset',
      token: 'token',
      workspaceSlug: 'workspace / one',
    });
    expect(apiFetchJson).toHaveBeenLastCalledWith(
      '/api/v1/workspaces/workspace%20%2F%20one/legacy-issues/grid-preferences/dataset/aircon%20%2F%20current',
      'token',
    );

    await updateLegacyIssueGridPreference({
      expectedRevision: 7,
      gridKey: 'aircon',
      gridKind: 'vehicle-module-checklist',
      payload: {
        column_order: ['status', 'problem'],
        frozen_column_count: 2,
        hidden_column_keys: ['problem'],
      },
      token: 'token',
      workspaceSlug: 'workspace',
    });
    expect(apiFetchJson).toHaveBeenLastCalledWith(
      '/api/v1/workspaces/workspace/legacy-issues/grid-preferences/vehicle-module-checklist/aircon',
      'token',
      {
        body: JSON.stringify({
          column_order: ['status', 'problem'],
          frozen_column_count: 2,
          hidden_column_keys: ['problem'],
          expected_revision: 7,
        }),
        method: 'PUT',
      },
    );

    await deleteLegacyIssueGridPreference({
      expectedRevision: 8,
      gridKey: 'aircon',
      gridKind: 'dataset',
      token: 'token',
      workspaceSlug: 'workspace',
    });
    expect(apiFetchJson).toHaveBeenLastCalledWith(
      '/api/v1/workspaces/workspace/legacy-issues/grid-preferences/dataset/aircon?expected_revision=8',
      'token',
      { method: 'DELETE' },
    );
  });
});
