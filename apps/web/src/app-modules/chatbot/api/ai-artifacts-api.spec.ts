import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  getAiArtifact,
  listAiArtifacts,
  listAiArtifactSources,
  listAiGraphRuns,
} from './ai-artifacts-api';

const apiFetchJson = vi.fn();

vi.mock('@/src/platform/api/client', () => ({
  apiFetchJson: (...args: unknown[]) => apiFetchJson(...args),
}));

describe('AI artifact API', () => {
  beforeEach(() => {
    apiFetchJson.mockReset();
  });

  it('requests and retains only completed report artifacts', async () => {
    apiFetchJson.mockResolvedValue({
      items: [
        {
          id: 'artifact-1',
          artifact_number: 4,
          graph_run_id: 'run-1',
          conversation_id: 'conversation-1',
          conversation_turn_id: 'turn-1',
          kind: 'report',
          status: 'completed',
          title: '접속 오류 보고서',
          content_markdown: '# 보고서',
          created_at: '2026-07-26T01:00:00Z',
          completed_at: '2026-07-26T01:01:00Z',
        },
        {
          id: 'artifact-2',
          kind: 'analysis',
          status: 'completed',
        },
      ],
      limit: 30,
      offset: 60,
      total: 1,
    });

    const response = await listAiArtifacts({
      appId: 'docs',
      conversationId: 'conversation / one',
      kind: 'report',
      limit: 30,
      offset: 60,
      status: 'completed',
      token: 'token',
      workspaceSlug: 'research / one',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research%20%2F%20one/ai/artifacts?limit=30&offset=60&artifact_type=report&status=completed&app_id=docs&conversation_id=conversation+%2F+one',
      'token',
      { signal: undefined },
    );
    expect(response.items).toEqual([
      {
        id: 'artifact-1',
        artifactNumber: 4,
        graphRunId: 'run-1',
        conversationId: 'conversation-1',
        conversationTurnId: 'turn-1',
        kind: 'report',
        status: 'completed',
        title: '접속 오류 보고서',
        contentMarkdown: '# 보고서',
        createdAt: '2026-07-26T01:00:00Z',
        completedAt: '2026-07-26T01:01:00Z',
      },
    ]);
  });

  it('normalizes rolling-deploy content, turn id, and closed status fallbacks', async () => {
    apiFetchJson.mockResolvedValue({
      id: 'legacy-artifact',
      run_id: 'run-legacy',
      conversation_id: 'conversation-legacy',
      turn_id: 'turn-legacy',
      kind: 'report',
      status: 'closed',
      title: 'Legacy report',
      content: '# Legacy',
    });

    const artifact = await getAiArtifact({
      artifactId: 'legacy/artifact',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research/ai/artifacts/legacy%2Fartifact',
      'token',
      { signal: undefined },
    );
    expect(artifact).toMatchObject({
      contentMarkdown: '# Legacy',
      conversationTurnId: 'turn-legacy',
      graphRunId: 'run-legacy',
      status: 'completed',
    });
  });

  it('normalizes the current artifact contract and building lifecycle', async () => {
    apiFetchJson.mockResolvedValue({
      id: 'artifact-current',
      artifact_number: 'AIR-000042',
      graph_run_id: 'run-current',
      conversation_id: 'conversation-current',
      conversation_turn_id: 'turn-current',
      artifact_type: 'report',
      status: 'building',
      title: 'Current report',
      content_text: '# Current',
    });

    const artifact = await getAiArtifact({
      artifactId: 'artifact-current',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(artifact).toMatchObject({
      artifactNumber: 'AIR-000042',
      contentMarkdown: '# Current',
      kind: 'report',
      status: 'running',
    });
  });

  it('normalizes source columns and row arrays for the source grid', async () => {
    apiFetchJson.mockResolvedValue({
      items: [
        {
          id: 'source-1',
          source_kind: 'query_result',
          title: '권역별 발생 건수',
          columns: ['region', { key: 'count', label: '건수' }],
          rows: [
            ['중부', 12],
            ['남부', 8],
          ],
          row_count: 2,
          truncated: false,
          query_id: 'regional-count',
        },
      ],
    });

    const sources = await listAiArtifactSources({
      artifactId: 'report-1',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(sources[0]).toEqual({
      id: 'source-1',
      sourceKind: 'query_result',
      title: '권역별 발생 건수',
      columns: [
        { key: 'region', label: 'region' },
        { key: 'count', label: '건수' },
      ],
      rows: [
        { region: '중부', count: 12 },
        { region: '남부', count: 8 },
      ],
      rowCount: 2,
      truncated: false,
      queryId: 'regional-count',
    });
  });

  it('normalizes current source grid field names', async () => {
    apiFetchJson.mockResolvedValue({
      items: [
        {
          id: 'source-current',
          source_kind: 'query_result',
          title: '지역별 발생 건수',
          grid_columns: [
            { key: 'region', label: '지역' },
            { key: 'count', label: '건수' },
          ],
          grid_rows: [{ region: '서울', count: 9 }],
          row_count: 1,
        },
      ],
    });

    const sources = await listAiArtifactSources({
      artifactId: 'report-current',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(sources[0]).toMatchObject({
      columns: [
        { key: 'region', label: '지역' },
        { key: 'count', label: '건수' },
      ],
      rows: [{ region: '서울', count: 9 }],
      rowCount: 1,
    });
  });

  it('loads graph runs by conversation and normalizes progress', async () => {
    apiFetchJson.mockResolvedValue({
      items: [
        {
          id: 'run-1',
          conversation_id: 'conversation-1',
          status: 'in_progress',
          current_stage: 'report_writer',
          progress_percent: 140,
          artifact_id: null,
          error_code: null,
          created_at: '2026-07-26T01:00:00Z',
          updated_at: '2026-07-26T01:02:00Z',
        },
      ],
    });

    const response = await listAiGraphRuns({
      appId: 'docs',
      conversationId: 'conversation/1',
      token: 'token',
      workspaceSlug: 'research',
    });

    expect(apiFetchJson).toHaveBeenCalledWith(
      '/api/v1/workspaces/research/ai/graph-runs?conversation_id=conversation%2F1&app_id=docs',
      'token',
      { signal: undefined },
    );
    expect(response.items[0]).toMatchObject({
      status: 'running',
      progressPercent: 100,
      currentStage: 'report_writer',
    });
  });
});
