import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ChatThread } from './ChatThread';

describe('ChatThread', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
      writable: true,
    });
  });

  it('keeps the typing hint visible while no live text or artifacts have arrived', () => {
    render(
      <ChatThread
        turns={[]}
        liveAssistant={{
          content: '',
          reasoning: '',
          status: 'streaming',
          artifacts: [],
        }}
      />,
    );

    expect(screen.getByText('답변 작성 중')).not.toBeNull();
  });

  it('renders the live bubble as soon as an artifact starts streaming', () => {
    render(
      <ChatThread
        turns={[]}
        liveAssistant={{
          content: '',
          reasoning: '',
          status: 'streaming',
          artifacts: [
            {
              id: 'live-artifact',
              type: 'document',
              title: '초안',
              content: '본문',
              status: 'open',
            },
          ],
        }}
        onOpenArtifact={vi.fn()}
      />,
    );

    expect(screen.queryByText('답변 작성 중')).toBeNull();
    expect(screen.getByTestId('artifact-card-live-artifact')).not.toBeNull();
  });
});
