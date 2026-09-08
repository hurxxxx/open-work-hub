import { describe, expect, it, vi } from 'vitest';

import type { MeetingInsightItem } from '../../api/meeting-insights-api';

import {
  buildMeetingInsightConversationRequest,
  buildMeetingInsightDraftSourceKey,
  buildMeetingInsightPromptDraft,
  extractMeetingInsightTitle,
  planMeetingInsightChatHandoff,
  type MeetingInsightChatTranslator,
} from './meeting-insight-chat-handoff';

function makeInsight(
  overrides: Partial<MeetingInsightItem>,
): MeetingInsightItem {
  return {
    id: 'insight-1',
    meeting_id: 'meeting-1',
    recording_id: null,
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

function makeTranslator() {
  return vi.fn<MeetingInsightChatTranslator>((key, variables) =>
    [key, variables.meetingTitle, variables.label].join('|'),
  );
}

describe('meeting insight chat handoff plan', () => {
  it('plans scoped conversation creation, draft state, and encoded target URL', () => {
    const translate = makeTranslator();
    const plan = planMeetingInsightChatHandoff({
      meeting: { id: 'meeting-1', title: 'Weekly Sync' },
      insight: makeInsight({
        id: 'action-1',
        insight_type: 'action',
        payload: { title: '로그인 플로우 정리' },
      }),
      translate,
    });

    expect(plan.conversationRequest).toEqual({
      scopeRef: 'meeting',
      scopeResourceId: 'meeting-1',
    });
    expect(plan.locationState).toEqual({
      aiDraft:
        'apps:meeting.insightChat.actionPrompt|Weekly Sync|로그인 플로우 정리',
      aiDraftSourceKey: 'meeting-insight:meeting-1:action-1',
      aiDraftOrigin: 'meeting_insight',
    });
    expect(plan.targetUrlForConversation('conversation 1/2')).toBe(
      '/apps/chatbot?c=conversation+1%2F2',
    );
  });

  it.each([
    [
      'action',
      { title: '액션' },
      '액션',
      'apps:meeting.insightChat.actionPrompt',
    ],
    [
      'decision',
      { statement: '결정' },
      '결정',
      'apps:meeting.insightChat.decisionPrompt',
    ],
    [
      'followup_schedule',
      { proposed_title: '후속 회의' },
      '후속 회의',
      'apps:meeting.insightChat.followupPrompt',
    ],
  ] as const)(
    'uses the %s payload label and prompt key',
    (insightType, payload, expectedLabel, expectedPromptKey) => {
      const translate = makeTranslator();
      const insight = makeInsight({
        insight_type: insightType,
        payload,
      });

      expect(extractMeetingInsightTitle(insight)).toBe(expectedLabel);
      expect(
        buildMeetingInsightPromptDraft('Weekly Sync', insight, translate),
      ).toBe(`${expectedPromptKey}|Weekly Sync|${expectedLabel}`);
      expect(translate).toHaveBeenCalledWith(expectedPromptKey, {
        meetingTitle: 'Weekly Sync',
        label: expectedLabel,
      });
    },
  );

  it('ignores bogus flat insight keys when parsing the payload label', () => {
    const insight = makeInsight({
      insight_type: 'action',
      payload: { title: 'payload-sourced' },
      // @ts-expect-error - flat title is intentionally unsupported input.
      title: 'flat-sourced',
    });

    expect(extractMeetingInsightTitle(insight)).toBe('payload-sourced');
  });

  it('keeps unknown insight types inert while preserving source and scope plans', () => {
    const translate = makeTranslator();
    const insight = makeInsight({
      insight_type: 'unknown' as MeetingInsightItem['insight_type'],
      payload: { title: 'ignored' },
    });

    expect(extractMeetingInsightTitle(insight)).toBe('');
    expect(
      buildMeetingInsightPromptDraft('Weekly Sync', insight, translate),
    ).toBe('');
    expect(translate).not.toHaveBeenCalled();
    expect(buildMeetingInsightDraftSourceKey('meeting-1', insight.id)).toBe(
      'meeting-insight:meeting-1:insight-1',
    );
    expect(buildMeetingInsightConversationRequest('meeting-1')).toEqual({
      scopeRef: 'meeting',
      scopeResourceId: 'meeting-1',
    });
  });
});
