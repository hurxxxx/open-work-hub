import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  isAiGraphRunActive,
  latestAiGraphRun,
  useAiGraphRunRecovery,
} from './useAiGraphRunRecovery';

const mocks = vi.hoisted(() => ({
  listAiArtifacts: vi.fn(),
  listAiGraphRuns: vi.fn(),
}));

vi.mock('./ai-artifacts-api', () => ({
  listAiArtifacts: mocks.listAiArtifacts,
  listAiGraphRuns: mocks.listAiGraphRuns,
}));

describe('useAiGraphRunRecovery', () => {
  beforeEach(() => {
    mocks.listAiArtifacts.mockReset();
    mocks.listAiGraphRuns.mockReset();
    mocks.listAiArtifacts.mockResolvedValue({
      items: [],
      limit: 100,
      offset: 0,
      total: 0,
    });
  });

  it('restores the latest completed run and its report artifacts', async () => {
    mocks.listAiGraphRuns.mockResolvedValue({
      items: [
        graphRun({
          id: 'older-run',
          updatedAt: '2026-07-26T01:00:00Z',
        }),
        graphRun({
          id: 'latest-run',
          updatedAt: '2026-07-26T02:00:00Z',
        }),
      ],
      total: 2,
    });
    mocks.listAiArtifacts.mockResolvedValue({
      items: [
        {
          id: 'report-1',
          artifactNumber: 1,
          graphRunId: 'latest-run',
          conversationId: 'conversation-1',
          conversationTurnId: 'turn-1',
          kind: 'report',
          status: 'completed',
          title: '보고서',
          contentMarkdown: '# 보고서',
          createdAt: '2026-07-26T02:00:00Z',
          completedAt: '2026-07-26T02:01:00Z',
        },
      ],
      limit: 100,
      offset: 0,
      total: 1,
    });

    const rendered = renderHook(() =>
      useAiGraphRunRecovery({
        appId: 'legacy-issues',
        conversationId: 'conversation-1',
        enabled: true,
        token: 'token',
        workspaceSlug: 'research',
      }),
    );

    await waitFor(() => {
      expect(rendered.result.current.run?.id).toBe('latest-run');
    });
    expect(rendered.result.current.artifacts).toEqual([
      expect.objectContaining({
        content: '# 보고서',
        id: 'report-1',
        kind: 'report',
        status: 'closed',
        type: 'document',
      }),
    ]);
    expect(mocks.listAiArtifacts).toHaveBeenCalledWith(
      expect.objectContaining({
        appId: 'legacy-issues',
        conversationId: 'conversation-1',
        kind: 'report',
        status: 'completed',
      }),
    );
  });

  it('does not query durable endpoints when recovery is disabled', () => {
    renderHook(() =>
      useAiGraphRunRecovery({
        appId: 'legacy-issues',
        conversationId: 'conversation-1',
        enabled: false,
        token: 'token',
        workspaceSlug: 'research',
      }),
    );

    expect(mocks.listAiGraphRuns).not.toHaveBeenCalled();
    expect(mocks.listAiArtifacts).not.toHaveBeenCalled();
  });

  it('refreshes durable state when a new chat transport run changes state', async () => {
    mocks.listAiGraphRuns.mockResolvedValue({
      items: [graphRun({ id: 'run-before' })],
      total: 1,
    });
    const rendered = renderHook(
      ({ refreshKey }) =>
        useAiGraphRunRecovery({
          appId: 'legacy-issues',
          conversationId: 'conversation-1',
          enabled: true,
          refreshKey,
          token: 'token',
          workspaceSlug: 'research',
        }),
      { initialProps: { refreshKey: 'idle' } },
    );

    await waitFor(() => {
      expect(rendered.result.current.run?.id).toBe('run-before');
    });
    mocks.listAiGraphRuns.mockResolvedValue({
      items: [graphRun({ id: 'run-after', status: 'running' })],
      total: 1,
    });

    rendered.rerender({ refreshKey: 'done' });

    await waitFor(() => {
      expect(rendered.result.current.run?.id).toBe('run-after');
    });
  });
});

describe('AI graph run recovery model', () => {
  it('selects the most recently updated run and recognizes active states', () => {
    const latest = latestAiGraphRun([
      graphRun({ id: 'older', updatedAt: '2026-07-26T01:00:00Z' }),
      graphRun({
        id: 'newer',
        status: 'running',
        updatedAt: '2026-07-26T02:00:00Z',
      }),
    ]);

    expect(latest?.id).toBe('newer');
    expect(isAiGraphRunActive(latest)).toBe(true);
  });

  it('prefers an active run over a recently updated terminal run', () => {
    const latest = latestAiGraphRun([
      graphRun({
        id: 'completed',
        status: 'completed',
        updatedAt: '2026-07-26T03:00:00Z',
      }),
      graphRun({
        id: 'active',
        status: 'running',
        updatedAt: '2026-07-26T02:00:00Z',
      }),
    ]);

    expect(latest?.id).toBe('active');
  });
});

function graphRun(overrides: Partial<ReturnType<typeof baseGraphRun>> = {}) {
  return { ...baseGraphRun(), ...overrides };
}

function baseGraphRun() {
  return {
    id: 'run-1',
    conversationId: 'conversation-1',
    status: 'completed',
    currentStage: null,
    progressPercent: 100,
    artifactId: 'report-1',
    errorCode: null,
    createdAt: '2026-07-26T01:00:00Z',
    updatedAt: '2026-07-26T01:01:00Z',
  };
}
