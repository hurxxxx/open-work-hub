import { useEffect, useMemo, useState } from 'react';

import { ApiRequestError } from '@/src/platform/api/client';
import type { ArtifactBuffer } from './agent-events';
import {
  listAiArtifacts,
  listAiGraphRuns,
  type AiArtifact,
  type AiGraphRun,
} from './ai-artifacts-api';

const ACTIVE_RUN_POLL_INTERVAL_MS = 2_000;

export interface AiGraphRunRecoveryState {
  artifacts: ArtifactBuffer[];
  loading: boolean;
  run: AiGraphRun | null;
  supported: boolean | null;
}

const INITIAL_STATE: AiGraphRunRecoveryState = {
  artifacts: [],
  loading: false,
  run: null,
  supported: null,
};

export function useAiGraphRunRecovery({
  appId,
  conversationId,
  enabled,
  refreshKey,
  token,
  workspaceSlug,
}: {
  appId: string;
  conversationId: string | null;
  enabled: boolean;
  refreshKey?: string | number | null;
  token: string | null;
  workspaceSlug?: string | null;
}): AiGraphRunRecoveryState {
  const [state, setState] = useState<AiGraphRunRecoveryState>(INITIAL_STATE);
  const ownerKey = useMemo(
    () =>
      enabled && token && workspaceSlug && conversationId
        ? `${workspaceSlug}:${appId}:${conversationId}`
        : null,
    [appId, conversationId, enabled, token, workspaceSlug],
  );

  useEffect(() => {
    if (!ownerKey || !token || !workspaceSlug || !conversationId) {
      setState(INITIAL_STATE);
      return;
    }

    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const load = async () => {
      controller?.abort();
      controller = new AbortController();
      setState((current) => ({
        ...current,
        loading: current.supported === null,
      }));
      try {
        const response = await listAiGraphRuns({
          appId,
          conversationId,
          signal: controller.signal,
          token,
          workspaceSlug,
        });
        if (cancelled) return;
        const run = latestAiGraphRun(response.items);
        const artifacts = await loadCompletedReportArtifacts({
          appId,
          conversationId,
          signal: controller.signal,
          token,
          workspaceSlug,
        });
        if (cancelled) return;
        setState({
          artifacts,
          loading: false,
          run,
          supported: true,
        });
        if (run && isAiGraphRunActive(run)) {
          pollTimer = setTimeout(load, ACTIVE_RUN_POLL_INTERVAL_MS);
        }
      } catch (error) {
        if (cancelled || (error as Error).name === 'AbortError') return;
        if (error instanceof ApiRequestError && error.status === 404) {
          setState({
            artifacts: [],
            loading: false,
            run: null,
            supported: false,
          });
          return;
        }
        setState((current) => ({
          ...current,
          loading: false,
          supported: current.supported ?? true,
        }));
        pollTimer = setTimeout(load, ACTIVE_RUN_POLL_INTERVAL_MS);
      }
    };

    setState(INITIAL_STATE);
    void load();
    return () => {
      cancelled = true;
      controller?.abort();
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [appId, conversationId, ownerKey, refreshKey, token, workspaceSlug]);

  return state;
}

export function latestAiGraphRun(runs: AiGraphRun[]): AiGraphRun | null {
  const activeRuns = runs.filter(isAiGraphRunActive);
  const candidates = activeRuns.length > 0 ? activeRuns : runs;
  return (
    [...candidates].sort(
      (left, right) => runTimestamp(right) - runTimestamp(left),
    )[0] ?? null
  );
}

export function isAiGraphRunActive(run: AiGraphRun | null): boolean {
  return run?.status === 'queued' || run?.status === 'running';
}

export function aiArtifactToBuffer(artifact: AiArtifact): ArtifactBuffer {
  return {
    id: artifact.id,
    type: 'document',
    title: artifact.title || null,
    language: null,
    content: artifact.contentMarkdown,
    status: artifact.status === 'completed' ? 'closed' : 'open',
    kind: artifact.kind,
    graphRunId: artifact.graphRunId,
    conversationId: artifact.conversationId,
    conversationTurnId: artifact.conversationTurnId,
    createdAt: artifact.createdAt,
    completedAt: artifact.completedAt,
  };
}

async function loadCompletedReportArtifacts({
  appId,
  conversationId,
  signal,
  token,
  workspaceSlug,
}: {
  appId: string;
  conversationId: string;
  signal: AbortSignal;
  token: string;
  workspaceSlug: string;
}): Promise<ArtifactBuffer[]> {
  const response = await listAiArtifacts({
    appId,
    conversationId,
    kind: 'report',
    limit: 100,
    offset: 0,
    signal,
    status: 'completed',
    token,
    workspaceSlug,
  });
  return response.items.map(aiArtifactToBuffer);
}

function runTimestamp(run: AiGraphRun): number {
  const value = run.updatedAt ?? run.createdAt;
  if (!value) return 0;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : 0;
}
