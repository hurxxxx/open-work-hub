import { describe, expect, it } from 'vitest';

import type { ArtifactBuffer } from '../api/agent-events';
import type { ChatTurn } from './chat/chat-turn';
import { collectArtifacts } from './chat-turn-model';

describe('collectArtifacts', () => {
  it('adds durable metadata without erasing persisted report content', () => {
    const persisted: ArtifactBuffer = {
      id: 'report-1',
      type: 'document',
      title: 'Persisted report',
      content: '# Final report',
      status: 'closed',
      conversationTurnId: 'turn-1',
    };
    const turns: ChatTurn[] = [
      {
        id: 'turn-1',
        role: 'assistant',
        content: '',
        artifacts: [persisted],
      },
    ];

    expect(
      collectArtifacts(turns, [
        {
          id: 'report-1',
          type: 'document',
          title: 'Recovered report',
          content: '',
          status: 'closed',
          kind: 'report',
          graphRunId: 'run-1',
        },
      ]),
    ).toEqual([
      expect.objectContaining({
        content: '# Final report',
        conversationTurnId: 'turn-1',
        graphRunId: 'run-1',
        kind: 'report',
        title: 'Recovered report',
      }),
    ]);
  });
});
