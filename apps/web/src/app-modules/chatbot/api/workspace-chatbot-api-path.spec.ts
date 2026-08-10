import { describe, expect, it } from 'vitest';

import { resetWorkspaceApiRoutePolicy } from '@/src/platform/api/workspace-api-path-policy';
import { resolveWorkspaceChatbotApiPath } from './workspace-chatbot-api-path';

describe('resolveWorkspaceChatbotApiPath', () => {
  it('builds the canonical workspace-scoped chatbot path without relying on route policy prefixes', () => {
    resetWorkspaceApiRoutePolicy();

    expect(
      resolveWorkspaceChatbotApiPath(
        '/api/v1/chatbot/conversations?limit=50',
        'general',
      ),
    ).toBe('/api/v1/workspaces/general/chatbot/conversations?limit=50');
  });

  it('leaves chatbot paths unchanged when there is no workspace slug', () => {
    resetWorkspaceApiRoutePolicy();

    expect(resolveWorkspaceChatbotApiPath('/api/v1/chatbot/health')).toBe(
      '/api/v1/chatbot/health',
    );
  });
});
