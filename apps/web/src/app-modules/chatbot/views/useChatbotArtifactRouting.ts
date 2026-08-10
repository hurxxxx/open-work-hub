import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { ArtifactBuffer } from '../api/agent-events';
import {
  buildArtifactSearchParams,
  collectArtifacts,
  resolveActiveArtifact,
  resolveAutoOpenArtifactId,
  shouldClearMissingArtifactQuery,
} from './chatbot-view-model';
import type { ChatTurn } from './chat/MessageBubble';

function createBrowserSearchParams(): URLSearchParams {
  return new URLSearchParams(
    typeof window === 'undefined' ? '' : window.location.search,
  );
}

export function useChatbotArtifactRouting({
  autoOpenArtifacts = true,
  isConversationReady,
  isLoadingConversation,
  isSending,
  liveArtifacts,
  recoveredArtifacts,
  sourceArtifactTypes,
  turns,
}: {
  autoOpenArtifacts?: boolean;
  isConversationReady: boolean;
  isLoadingConversation: boolean;
  isSending: boolean;
  liveArtifacts: ArtifactBuffer[];
  recoveredArtifacts?: ArtifactBuffer[];
  sourceArtifactTypes?: readonly string[];
  turns: ChatTurn[];
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const routeArtifactId = searchParams.get('a');

  const writeArtifactRouteSearchParams = useCallback(
    ({
      artifactId,
      replace,
      sourceSearchParams,
    }: {
      artifactId: string | null;
      replace: boolean;
      sourceSearchParams: URLSearchParams;
    }) => {
      setSearchParams(
        buildArtifactSearchParams(sourceSearchParams, artifactId),
        {
          replace,
        },
      );
    },
    [setSearchParams],
  );

  const allArtifacts = useMemo(() => {
    return collectArtifacts(turns, [
      ...(recoveredArtifacts ?? []),
      ...liveArtifacts,
    ]);
  }, [liveArtifacts, recoveredArtifacts, turns]);
  const visibleLiveArtifacts = useMemo(() => {
    const sourceTypes = new Set(sourceArtifactTypes ?? []);
    return liveArtifacts.filter((artifact) => !sourceTypes.has(artifact.type));
  }, [liveArtifacts, sourceArtifactTypes]);

  const activeArtifact = useMemo(() => {
    return resolveActiveArtifact({
      artifacts: allArtifacts,
      routeArtifactId,
    });
  }, [allArtifacts, routeArtifactId]);

  useEffect(() => {
    if (
      !shouldClearMissingArtifactQuery({
        activeArtifact,
        isConversationReady,
        isLoadingConversation,
        isSending,
        routeArtifactId,
      })
    ) {
      return;
    }
    writeArtifactRouteSearchParams({
      artifactId: null,
      replace: true,
      sourceSearchParams: searchParams,
    });
  }, [
    activeArtifact,
    isConversationReady,
    isLoadingConversation,
    isSending,
    routeArtifactId,
    searchParams,
    writeArtifactRouteSearchParams,
  ]);

  const lastAutoOpenedArtifactRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoOpenArtifacts) {
      return;
    }
    const artifactId = resolveAutoOpenArtifactId({
      lastAutoOpenedArtifactId: lastAutoOpenedArtifactRef.current,
      liveArtifacts: visibleLiveArtifacts,
      routeArtifactId,
    });
    if (!artifactId) {
      return;
    }
    lastAutoOpenedArtifactRef.current = artifactId;
    writeArtifactRouteSearchParams({
      artifactId,
      replace: true,
      sourceSearchParams: createBrowserSearchParams(),
    });
  }, [
    autoOpenArtifacts,
    routeArtifactId,
    visibleLiveArtifacts,
    writeArtifactRouteSearchParams,
  ]);

  const handleOpenArtifact = useCallback(
    (artifactId: string) => {
      if (artifactId === routeArtifactId) {
        return;
      }
      writeArtifactRouteSearchParams({
        artifactId,
        replace: false,
        sourceSearchParams: searchParams,
      });
    },
    [routeArtifactId, searchParams, writeArtifactRouteSearchParams],
  );

  const handleCloseArtifact = useCallback(() => {
    if (!routeArtifactId) {
      return;
    }
    writeArtifactRouteSearchParams({
      artifactId: null,
      replace: false,
      sourceSearchParams: searchParams,
    });
  }, [routeArtifactId, searchParams, writeArtifactRouteSearchParams]);

  return {
    activeArtifact,
    allArtifacts,
    handleCloseArtifact,
    handleOpenArtifact,
    routeArtifactId,
  };
}
