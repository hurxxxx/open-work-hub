import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  configureWorkspaceApiRoutePolicy,
  resetWorkspaceApiRoutePolicy,
} from '@/src/platform/api/workspace-api-path-policy';
import { ApiRequestError } from '@/src/platform/api/client';
import { createWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-route-policy';
import {
  downloadPatentPriorArtArtifact,
  downloadPatentPriorArtReport,
  getPatentPriorArtConfig,
  previewPatentPriorArtQuery,
  type PatentPriorArtCandidate,
} from './patent-prior-art-api';

describe('patent prior art API', () => {
  beforeEach(() => {
    configureWorkspaceApiRoutePolicy(
      createWorkspaceApiRoutePolicy({
        platformPrefixes: [],
        sources: [
          {
            contract: {
              workspaceApiPrefixes: ['/api/v1/patent-prior-art'],
            },
          },
        ],
      }),
    );
  });

  afterEach(() => {
    resetWorkspaceApiRoutePolicy();
    vi.unstubAllGlobals();
  });

  it('uses the workspace path rewrite for config requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          allowed_upload_extensions: ['.pdf'],
          categories: [],
          jurisdictions: [],
          max_invention_chars: 200_000,
          max_plan_value_chars: 256,
          max_plan_values_per_field: 30,
          max_upload_bytes: 1024,
          min_invention_chars: 30,
          report_formats: [
            'html',
            'pdf',
            'docx',
            'summary_pdf',
            'summary_docx',
          ],
          visual_extraction_available: false,
        }),
        { headers: { 'Content-Type': 'application/json' }, status: 200 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await getPatentPriorArtConfig({ token: 'token', workspaceSlug: 'r-and-d' });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/r-and-d/patent-prior-art/config',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('sends only typed category, jurisdiction, and invention inputs to preview', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          plan: {},
          source_queries: [],
          technology_summary: '',
        }),
        { headers: { 'Content-Type': 'application/json' }, status: 200 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    await previewPatentPriorArtQuery({
      request: {
        category_ids: ['vehicle'],
        invention_text: 'A sufficiently detailed invention description.',
        jurisdictions: ['KR'],
      },
      token: 'token',
      workspaceSlug: 'ws',
    });

    const [, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(request.body))).toEqual({
      category_ids: ['vehicle'],
      invention_text: 'A sufficiently detailed invention description.',
      jurisdictions: ['KR'],
    });
  });

  it('downloads artifacts from encoded workspace-scoped identifiers', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('report', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const blob = await downloadPatentPriorArtArtifact({
      artifactId: 'report/markdown',
      jobId: 'job/42',
      token: 'token',
      workspaceSlug: 'ws',
    });

    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/ws/patent-prior-art/jobs/job%2F42/artifacts/report%2Fmarkdown',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('downloads a typed report from the workspace-scoped report path', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('report', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const blob = await downloadPatentPriorArtReport({
      jobId: 'job/42',
      reportFormat: 'summary_docx',
      token: 'token',
      workspaceSlug: 'ws',
    });

    expect(blob).toBeInstanceOf(Blob);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/workspaces/ws/patent-prior-art/jobs/job%2F42/reports/summary_docx',
      expect.objectContaining({ cache: 'no-store' }),
    );
  });

  it('surfaces report download errors as ApiRequestError', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Report unavailable' }), {
        headers: { 'Content-Type': 'application/json' },
        status: 404,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const request = downloadPatentPriorArtReport({
      jobId: 'job-42',
      reportFormat: 'pdf',
      token: 'token',
      workspaceSlug: 'ws',
    });

    await expect(request).rejects.toBeInstanceOf(ApiRequestError);
    await expect(request).rejects.toMatchObject({
      message: 'report_download_failed',
      payload: { detail: 'Report unavailable' },
      status: 404,
    });
  });

  it('keeps public candidate display fields rank-based', () => {
    const candidate: PatentPriorArtCandidate = {
      jurisdiction: 'KR',
      publication_number: 'KR-2026-0000001',
      rank: 1,
      relevance_band: 'high',
      title: 'Candidate',
    };

    expect(candidate).toMatchObject({ rank: 1, relevance_band: 'high' });
    expect(candidate).not.toHaveProperty('score');
  });
});
