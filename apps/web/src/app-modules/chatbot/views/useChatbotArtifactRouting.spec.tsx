import { act, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { ArtifactBuffer } from '../api/agent-events';
import { useChatbotArtifactRouting } from './useChatbotArtifactRouting';

const completedArtifact: ArtifactBuffer = {
  content: '{"version":1,"sources":[]}',
  id: 'sources-1',
  language: null,
  status: 'closed',
  title: 'Sources',
  type: 'files-rag-sources',
};

function RoutingHarness({
  autoOpenArtifacts,
}: {
  autoOpenArtifacts?: boolean;
}) {
  const location = useLocation();
  useChatbotArtifactRouting({
    autoOpenArtifacts,
    isConversationReady: true,
    isLoadingConversation: false,
    isSending: false,
    liveArtifacts: [completedArtifact],
    turns: [],
  });
  return <div data-testid="search">{location.search}</div>;
}

describe('useChatbotArtifactRouting', () => {
  it('keeps auto-open enabled by default', async () => {
    render(
      <MemoryRouter>
        <RoutingHarness />
      </MemoryRouter>,
    );

    await act(async () => undefined);
    expect(screen.getByTestId('search').textContent).toBe('?a=sources-1');
  });

  it('keeps artifact cards closed when auto-open is disabled', async () => {
    render(
      <MemoryRouter>
        <RoutingHarness autoOpenArtifacts={false} />
      </MemoryRouter>,
    );

    await act(async () => undefined);
    expect(screen.getByTestId('search').textContent).toBe('');
  });
});
