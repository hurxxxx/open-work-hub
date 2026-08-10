import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createLegacyIssueVehicleModel,
  createLegacyIssueVehicleModuleChecklist,
  createLegacyIssueVehicleStage,
  deleteLegacyIssueVehicleModuleChecklistAttachment,
  deleteLegacyIssueVehicleChecklistRevision,
  deleteLegacyIssueVehicleModuleChecklist,
  fetchLegacyIssueVehicleModuleChecklistAttachmentBlob,
  fetchLegacyIssueVehicleChecklistModules,
  fetchLegacyIssueVehicleModuleChecklists,
  fetchLegacyIssueVehicleModuleChecklistRecords,
  importPreviousStageLegacyIssueVehicleModuleChecklist,
  permanentlyDeleteLegacyIssueVehicleModel,
  saveLegacyIssueVehicleModuleChecklistRecords,
  updateLegacyIssueVehicleStage,
  uploadLegacyIssueVehicleModuleChecklistAttachment,
} from './legacy-issue-vehicle-api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('legacy issue vehicle checklist API', () => {
  it('permanently deletes a vehicle model through the dedicated endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await permanentlyDeleteLegacyIssueVehicleModel({
      token: 'token',
      vehicleModelId: 'vehicle/17',
      workspaceSlug: 'research team',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-models/vehicle%2F17/permanent',
      expect.objectContaining({
        cache: 'no-store',
        method: 'DELETE',
      }),
    );
  });

  it('creates a vehicle with its initial stage and adds a later stage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'created' }), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await createLegacyIssueVehicleModel({
      initialStageName: 'P0',
      notes: 'Pilot',
      token: 'token',
      vehicleCode: 'MX5',
      vehicleName: 'Santa Fe',
      workspaceSlug: 'research',
    });
    await createLegacyIssueVehicleStage({
      name: 'P1',
      token: 'token',
      vehicleModelId: 'vehicle/17',
      workspaceSlug: 'research team',
    });
    await updateLegacyIssueVehicleStage({
      name: 'Pilot 1',
      stageId: 'stage/1',
      token: 'token',
      vehicleModelId: 'vehicle/17',
      workspaceSlug: 'research team',
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research/legacy-issues/vehicle-models',
      expect.objectContaining({
        body: JSON.stringify({
          initial_stage_name: 'P0',
          notes: 'Pilot',
          vehicle_code: 'MX5',
          vehicle_name: 'Santa Fe',
        }),
        method: 'POST',
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-models/vehicle%2F17/stages',
      expect.objectContaining({
        body: JSON.stringify({ name: 'P1' }),
        method: 'POST',
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-models/vehicle%2F17/stages/stage%2F1',
      expect.objectContaining({
        body: JSON.stringify({ name: 'Pilot 1' }),
        method: 'PATCH',
      }),
    );
  });

  it('deletes a checklist revision through the workspace-scoped endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await deleteLegacyIssueVehicleChecklistRevision({
      revisionId: 'revision/17',
      token: 'token',
      workspaceSlug: 'research team',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-checklist-revisions/revision%2F17',
      expect.objectContaining({
        cache: 'no-store',
        method: 'DELETE',
      }),
    );
  });

  it('loads module summaries and module checklist records from scoped endpoints', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [] }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            checklist: { id: 'check/17' },
            definition: {},
            items: [],
            limit: null,
            offset: 0,
            total: 0,
          }),
          { headers: { 'Content-Type': 'application/json' }, status: 200 },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    await fetchLegacyIssueVehicleChecklistModules({
      stageId: 'stage/1',
      token: 'token',
      vehicleModelId: 'MX/5',
      workspaceSlug: 'research team',
    });
    await fetchLegacyIssueVehicleModuleChecklistRecords({
      checklistId: 'check/17',
      query: 'check plan',
      token: 'token',
      workspaceSlug: 'research team',
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-models/MX%2F5/checklist-modules?stage_id=stage%2F1',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-module-checklists/check%2F17/records?q=check+plan',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('creates, patches, and permanently deletes a module checklist', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: 'check-17' }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [], updated: 1 }), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);

    await createLegacyIssueVehicleModuleChecklist({
      moduleKey: 'compressor/electric',
      sourceMasterRevisionId: 'master-17',
      stageId: 'stage-p1',
      token: 'token',
      vehicleModelId: 'MX5',
      workspaceSlug: 'research',
    });
    await saveLegacyIssueVehicleModuleChecklistRecords({
      checklistId: 'check-17',
      token: 'token',
      updates: [
        {
          record_id: 'record-1',
          values: { check_plan: 'Inspect' },
        },
      ],
      workspaceSlug: 'research',
    });
    await deleteLegacyIssueVehicleModuleChecklist({
      checklistId: 'check-17',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research/legacy-issues/vehicle-models/MX5/checklist-modules/compressor%2Felectric/checklists',
      expect.objectContaining({
        body: JSON.stringify({
          source_master_revision_id: 'master-17',
          stage_id: 'stage-p1',
        }),
        method: 'POST',
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research/legacy-issues/vehicle-module-checklists/check-17/records',
      expect.objectContaining({
        body: JSON.stringify({
          updates: [
            {
              record_id: 'record-1',
              values: { check_plan: 'Inspect' },
            },
          ],
        }),
        method: 'PATCH',
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/workspaces/research/legacy-issues/vehicle-module-checklists/check-17',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('loads module checklists for the selected vehicle stage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [],
          latest_master_revision: null,
          master_revisions: [],
        }),
        { headers: { 'Content-Type': 'application/json' }, status: 200 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchLegacyIssueVehicleModuleChecklists({
      moduleKey: 'aircon',
      stageId: 'stage/p1',
      token: 'token',
      vehicleModelId: 'MX5',
      workspaceSlug: 'research',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/research/legacy-issues/vehicle-models/MX5/checklist-modules/aircon/checklists?stage_id=stage%2Fp1',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('uploads, downloads, and deletes checklist record attachments', async () => {
    const attachment = {
      checklist_id: 'check/17',
      content_type: 'text/plain',
      created_at: '2026-07-15T00:00:00Z',
      filename: 'evidence.txt',
      id: 'attachment/1',
      record_id: 'record/1',
      size_bytes: 8,
      uploaded_by_id: 'user-1',
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(attachment), {
          headers: { 'Content-Type': 'application/json' },
          status: 201,
        }),
      )
      .mockResolvedValueOnce(new Response(new Blob(['evidence'])))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    const file = new File(['evidence'], 'evidence.txt', {
      type: 'text/plain',
    });

    await uploadLegacyIssueVehicleModuleChecklistAttachment({
      checklistId: 'check/17',
      file,
      recordId: 'record/1',
      token: 'token',
      workspaceSlug: 'research team',
    });
    const blob = await fetchLegacyIssueVehicleModuleChecklistAttachmentBlob({
      attachmentId: 'attachment/1',
      checklistId: 'check/17',
      token: 'token',
      workspaceSlug: 'research team',
    });
    await deleteLegacyIssueVehicleModuleChecklistAttachment({
      attachmentId: 'attachment/1',
      checklistId: 'check/17',
      token: 'token',
      workspaceSlug: 'research team',
    });

    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-module-checklists/check%2F17/records/record%2F1/attachments',
      expect.objectContaining({ body: expect.any(FormData), method: 'POST' }),
    );
    const uploadBody = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(uploadBody.get('file')).toBe(file);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-module-checklists/check%2F17/attachments/attachment%2F1/file',
      expect.objectContaining({ cache: 'no-store' }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-module-checklists/check%2F17/attachments/attachment%2F1',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });

  it('imports the completed checklist from the previous vehicle stage', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'imported-checklist' }), {
        headers: { 'Content-Type': 'application/json' },
        status: 201,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await importPreviousStageLegacyIssueVehicleModuleChecklist({
      moduleKey: 'electrical/mechanical',
      sourceChecklistId: 'check/source',
      stageId: 'stage/p1',
      token: 'token',
      vehicleModelId: 'MX/5',
      workspaceSlug: 'research team',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20team/legacy-issues/vehicle-models/MX%2F5/checklist-modules/electrical%2Fmechanical/checklists/import-previous-stage',
      expect.objectContaining({
        body: JSON.stringify({
          source_checklist_id: 'check/source',
          stage_id: 'stage/p1',
        }),
        method: 'POST',
      }),
    );
  });
});
