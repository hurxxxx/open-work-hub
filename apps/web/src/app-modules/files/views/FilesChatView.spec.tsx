import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ChatbotExperienceConfig } from '@/src/app-modules/chatbot/public-api';
import { FilesChatView } from './FilesChatView';

const chatbotView = vi.fn(
  (_props: { experience?: ChatbotExperienceConfig }) => null,
);

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/src/app-modules/chatbot/public-api', () => ({
  ChatbotView: (props: { experience?: ChatbotExperienceConfig }) =>
    chatbotView(props),
}));

describe('FilesChatView', () => {
  it('binds common chat to the Files workspace scope without auto-opening sources', () => {
    render(<FilesChatView />);

    expect(chatbotView).toHaveBeenCalledTimes(1);
    expect(chatbotView.mock.calls[0]?.[0].experience).toMatchObject({
      autoOpenArtifacts: false,
      conversationScope: {
        ref: 'files',
        resourceId: 'workspace',
      },
      emptyGreeting: 'files.chat.emptyGreeting',
      emptySubline: 'files.chat.emptySubline',
      routeAppId: 'files',
      routePathSuffix: '/chat',
      sidebarTitle: 'files.chat.conversationsTitle',
      title: 'files.chat.title',
    });
    expect(
      chatbotView.mock.calls[0]?.[0].experience?.artifactRenderers?.[0]?.type,
    ).toBe('files-rag-sources');
  });
});
