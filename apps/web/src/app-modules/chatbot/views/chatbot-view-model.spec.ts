import { describe, expect, it } from 'vitest';

import {
  buildAiChatStreamRequest,
  mergePendingUserTurn,
  resolveAutoOpenArtifactId,
} from './chatbot-view-model';
import type { ArtifactBuffer } from '../api/agent-events';
import type { ChatTurn } from './chat/chat-turn';

const turns: ChatTurn[] = [
  {
    id: 'turn-1',
    role: 'user',
    content: '접속 오류 관련 문제 찾아줘',
  },
];

describe('mergePendingUserTurn', () => {
  it('restores the pending question when route hydration reads no turns', () => {
    expect(
      mergePendingUserTurn({
        conversationId: 'conversation-1',
        pendingUserContent: '권역별 발생 건수를 비교해줘',
        turns: [],
      }),
    ).toEqual([
      expect.objectContaining({
        content: '권역별 발생 건수를 비교해줘',
        role: 'user',
        seq: 0,
      }),
    ]);
  });

  it('does not duplicate a pending question already returned by hydration', () => {
    const persistedUserTurn: ChatTurn = {
      id: 'persisted-user-1',
      content: '권역별 발생 건수를 비교해줘',
      role: 'user',
      seq: 0,
    };

    expect(
      mergePendingUserTurn({
        conversationId: 'conversation-1',
        pendingUserContent: '권역별 발생 건수를 비교해줘',
        turns: [persistedUserTurn],
      }),
    ).toEqual([persistedUserTurn]);
  });
});

describe('buildAiChatStreamRequest', () => {
  it('binds a fresh persisted chat to the configured conversation scope', () => {
    const request = buildAiChatStreamRequest({
      activeConversationId: null,
      allowedAppIds: [],
      backendMode: 'local',
      conversationScope: {
        ref: 'meeting',
        resourceId: 'meeting-1',
      },
      turns,
    });

    expect(request).toMatchObject({
      conversation_id: undefined,
      persist: true,
      scope_ref: 'meeting',
      scope_resource_id: 'meeting-1',
    });
  });

  it('does not resend scope fields when appending to an existing chat', () => {
    const request = buildAiChatStreamRequest({
      activeConversationId: 'conversation-1',
      allowedAppIds: [],
      backendMode: 'local',
      conversationScope: {
        ref: 'meeting',
        resourceId: 'meeting-1',
      },
      turns,
    });

    expect(request.conversation_id).toBe('conversation-1');
    expect('scope_ref' in request).toBe(false);
    expect('scope_resource_id' in request).toBe(false);
  });
});

describe('resolveAutoOpenArtifactId', () => {
  const htmlArtifact: ArtifactBuffer = {
    content: '<!doctype html><html><body>Hello</body></html>',
    id: 'artifact-html',
    language: null,
    status: 'open',
    title: 'HTML',
    type: 'html',
  };

  it('waits for a live artifact to complete before auto-opening it', () => {
    expect(
      resolveAutoOpenArtifactId({
        lastAutoOpenedArtifactId: null,
        liveArtifacts: [htmlArtifact],
        routeArtifactId: null,
      }),
    ).toBeNull();
  });

  it('auto-opens the first completed live artifact when a response has supporting artifacts', () => {
    const reportArtifact: ArtifactBuffer = {
      ...htmlArtifact,
      id: 'artifact-report',
      status: 'closed',
      title: 'Report',
      type: 'document',
    };
    const evidenceArtifact: ArtifactBuffer = {
      ...htmlArtifact,
      id: 'artifact-evidence',
      status: 'closed',
      title: 'Evidence',
      type: 'evidence',
    };

    expect(
      resolveAutoOpenArtifactId({
        lastAutoOpenedArtifactId: null,
        liveArtifacts: [reportArtifact, evidenceArtifact],
        routeArtifactId: null,
      }),
    ).toBe('artifact-report');
  });

  it('does not replace an artifact that is already open', () => {
    expect(
      resolveAutoOpenArtifactId({
        lastAutoOpenedArtifactId: 'artifact-report',
        liveArtifacts: [
          { ...htmlArtifact, id: 'artifact-report', status: 'closed' },
          { ...htmlArtifact, id: 'artifact-evidence', status: 'closed' },
        ],
        routeArtifactId: 'artifact-report',
      }),
    ).toBeNull();
  });

  it('opens a new response primary artifact when the route still points to an older response', () => {
    expect(
      resolveAutoOpenArtifactId({
        lastAutoOpenedArtifactId: 'artifact-previous-report',
        liveArtifacts: [
          { ...htmlArtifact, id: 'artifact-new-report', status: 'closed' },
          { ...htmlArtifact, id: 'artifact-new-evidence', status: 'closed' },
        ],
        routeArtifactId: 'artifact-previous-report',
      }),
    ).toBe('artifact-new-report');
  });
});
