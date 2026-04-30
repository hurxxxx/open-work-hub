import { describe, expect, it, vi } from 'vitest';

import type { MeetingInsightItem } from '../../api/meeting-insights-api';
import { createConversation } from '@/src/app-modules/ai/public-api';

import {
  __test,
  openMeetingInsightInChat,
} from './openMeetingInsightInChat';

vi.mock('@/src/app-modules/ai/public-api', () => ({
  createConversation: vi.fn(),
}));

function makeInsight(overrides: Partial<MeetingInsightItem>): MeetingInsightItem {
  return {
    id: 'insight-1',
    meeting_id: 'meeting-1',
    recording_id: null,
    workspace_id: 'workspace-1',
    insight_type: 'action',
    payload: {},
    confidence: null,
    source_span: null,
    status: 'draft',
    accepted_as_kind: null,
    accepted_as_id: null,
    created_by_run_id: null,
    created_at: '2026-04-21T00:00:00Z',
    ...overrides,
  };
}

describe('openMeetingInsightInChat', () => {
  it('builds an action draft from payload.title', async () => {
    const navigate = vi.fn();
    vi.mocked(createConversation).mockResolvedValue({
      id: 'conversation-1',
      title: '',
      scopeRef: 'meeting',
      scopeResourceId: 'meeting-1',
      turns: [],
      createdAt: '2026-04-21T00:00:00Z',
      updatedAt: '2026-04-21T00:00:00Z',
      livePendingApproval: null,
    });
    const insight = makeInsight({
      insight_type: 'action',
      payload: { title: '로그인 플로우 정리' },
    });

    await openMeetingInsightInChat({
      navigate,
      token: 'test-token',
      workspaceSlug: 'hq',
      meeting: { id: 'meeting-1', title: 'Weekly Sync' },
      insight,
    });

    expect(createConversation).toHaveBeenCalledWith('test-token', {
      scopeRef: 'meeting',
      scopeResourceId: 'meeting-1',
    });
    expect(navigate).toHaveBeenCalledTimes(1);
    const url = navigate.mock.calls[0]?.[0] as string;
    const options = navigate.mock.calls[0]?.[1] as
      | { state?: { aiDraft?: string; aiDraftSourceKey?: string; aiDraftOrigin?: string } }
      | undefined;
    expect(url).toBe('/w/hq/ai?c=conversation-1');
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('c')).toBe('conversation-1');
    expect(options?.state?.aiDraftOrigin).toBe('meeting_insight');
    expect(options?.state?.aiDraftSourceKey).toBe(
      'meeting-insight:meeting-1:insight-1',
    );
    expect(options?.state?.aiDraft).toContain('Weekly Sync');
  });

  it('uses payload.statement for decision insights', () => {
    const insight = makeInsight({
      insight_type: 'decision',
      payload: { statement: '신규 인증 흐름 채택' },
    });
    const draft = __test.buildPromptDraft('Weekly Sync', insight);
    expect(draft).toContain('결정사항');
    expect(draft).toContain('신규 인증 흐름 채택');
  });

  it('uses payload.proposed_title for followup insights', () => {
    const insight = makeInsight({
      insight_type: 'followup_schedule',
      payload: { proposed_title: '후속 점검 회의' },
    });
    const draft = __test.buildPromptDraft('Weekly Sync', insight);
    expect(draft).toContain('후속 회의 제안');
    expect(draft).toContain('후속 점검 회의');
  });

  it('does NOT rely on flat keys on the insight record', () => {
    // Guards D13: payload-based access. If a future refactor accidentally
    // reintroduces insight.title, this assertion makes the failure loud.
    const insight = makeInsight({
      insight_type: 'action',
      payload: { title: 'payload-sourced' },
      // @ts-expect-error — intentionally populate a bogus flat key to ensure the helper ignores it.
      title: 'flat-sourced',
    });
    expect(__test.extractInsightTitle(insight)).toBe('payload-sourced');
  });

  it('encodes special characters in workspaceSlug', async () => {
    const navigate = vi.fn();
    vi.mocked(createConversation).mockResolvedValue({
      id: 'conversation-1',
      title: '',
      scopeRef: 'meeting',
      scopeResourceId: 'meeting-1',
      turns: [],
      createdAt: '2026-04-21T00:00:00Z',
      updatedAt: '2026-04-21T00:00:00Z',
      livePendingApproval: null,
    });
    await openMeetingInsightInChat({
      navigate,
      token: 'test-token',
      workspaceSlug: 'team space',
      meeting: { id: 'meeting-1', title: 'Sync' },
      insight: makeInsight({
        insight_type: 'action',
        payload: { title: 'x' },
      }),
    });
    const url = navigate.mock.calls[0]?.[0] as string;
    expect(url.startsWith('/w/team%20space/ai?c=')).toBe(true);
  });
});
