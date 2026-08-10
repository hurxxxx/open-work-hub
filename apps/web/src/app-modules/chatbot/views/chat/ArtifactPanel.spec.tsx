import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBuffer } from '../../api/agent-events';
import { ArtifactPanel } from './ArtifactPanel';

describe('ArtifactPanel', () => {
  it('renders a durable artifact through its custom renderer before detail content loads', () => {
    const artifact: ArtifactBuffer = {
      id: 'report-1',
      type: 'document',
      title: 'Recovered report',
      content: '',
      status: 'closed',
      kind: 'report',
      graphRunId: 'run-1',
      conversationTurnId: 'turn-1',
    };
    const relatedSource: ArtifactBuffer = {
      id: 'source-1',
      type: 'legacy-issue-analysis',
      title: 'Source',
      content: '{}',
      status: 'closed',
      conversationTurnId: 'turn-1',
    };

    render(
      <ArtifactPanel
        artifact={artifact}
        artifacts={[artifact, relatedSource]}
        renderers={[
          {
            type: 'document',
            render: (_value, context) => (
              <div>
                Durable report · {context.relatedArtifacts.length} artifacts
              </div>
            ),
          },
        ]}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('Durable report · 2 artifacts')).not.toBeNull();
  });
});
