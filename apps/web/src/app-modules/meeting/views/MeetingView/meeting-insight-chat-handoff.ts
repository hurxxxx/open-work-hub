import { buildAppHref } from '@open-work-hub/contracts/app-routes';
import type { MeetingDetail } from '../../api/meeting-api';
import type {
  MeetingInsightItem,
  MeetingInsightType,
} from '../../api/meeting-insights-api';

export interface MeetingInsightChatPromptVariables
  extends Record<string, string> {
  meetingTitle: string;
  label: string;
}

export type MeetingInsightChatTranslator = (
  key: string,
  variables: MeetingInsightChatPromptVariables,
) => string;

export interface MeetingInsightChatConversationRequest {
  scopeRef: 'meeting';
  scopeResourceId: string;
}

export interface MeetingInsightDraftLocationState {
  aiDraft: string;
  aiDraftSourceKey: string;
  aiDraftOrigin: 'meeting_insight';
}

export interface MeetingInsightChatHandoffPlan {
  conversationRequest: MeetingInsightChatConversationRequest;
  locationState: MeetingInsightDraftLocationState;
  targetUrlForConversation: (conversationId: string) => string;
}

export interface PlanMeetingInsightChatHandoffArgs {
  meeting: Pick<MeetingDetail, 'id' | 'title'>;
  insight: MeetingInsightItem;
  translate: MeetingInsightChatTranslator;
}

const INSIGHT_TITLE_PAYLOAD_KEYS = {
  action: 'title',
  decision: 'statement',
  followup_schedule: 'proposed_title',
} satisfies Record<MeetingInsightType, string>;

const INSIGHT_PROMPT_KEYS = {
  action: 'apps:meeting.insightChat.actionPrompt',
  decision: 'apps:meeting.insightChat.decisionPrompt',
  followup_schedule: 'apps:meeting.insightChat.followupPrompt',
} satisfies Record<MeetingInsightType, string>;

function getInsightTitlePayloadKey(
  insightType: MeetingInsightItem['insight_type'],
): string | null {
  return INSIGHT_TITLE_PAYLOAD_KEYS[insightType] ?? null;
}

function getInsightPromptKey(
  insightType: MeetingInsightItem['insight_type'],
): string | null {
  return INSIGHT_PROMPT_KEYS[insightType] ?? null;
}

function readStringPayload(
  payload: Record<string, unknown>,
  key: string,
): string {
  const value = payload[key];
  return typeof value === 'string' ? value : '';
}

/**
 * Pull the primary title/label out of a raw ``MeetingInsightItem``.
 * Payload shape is type-dependent (see backend ``_serialize_insight``),
 * so callers should branch on ``insight_type`` rather than trusting flat
 * keys on the outer record.
 */
export function extractMeetingInsightTitle(
  insight: MeetingInsightItem,
): string {
  const key = getInsightTitlePayloadKey(insight.insight_type);
  return key ? readStringPayload(insight.payload, key) : '';
}

export function buildMeetingInsightPromptDraft(
  meetingTitle: string,
  insight: MeetingInsightItem,
  translate: MeetingInsightChatTranslator,
): string {
  const promptKey = getInsightPromptKey(insight.insight_type);
  if (!promptKey) {
    return '';
  }
  return translate(promptKey, {
    meetingTitle,
    label: extractMeetingInsightTitle(insight),
  });
}

export function buildMeetingInsightDraftSourceKey(
  meetingId: string,
  insightId: string,
): string {
  return `meeting-insight:${meetingId}:${insightId}`;
}

export function buildMeetingInsightConversationRequest(
  meetingId: string,
): MeetingInsightChatConversationRequest {
  return {
    scopeRef: 'meeting',
    scopeResourceId: meetingId,
  };
}

export function buildMeetingInsightChatTargetUrl(
  conversationId: string,
): string {
  return buildAppHref({
    routeId: 'chatbot.root',
    queryParams: { c: conversationId },
  });
}

export function planMeetingInsightChatHandoff({
  meeting,
  insight,
  translate,
}: PlanMeetingInsightChatHandoffArgs): MeetingInsightChatHandoffPlan {
  return {
    conversationRequest: buildMeetingInsightConversationRequest(meeting.id),
    locationState: {
      aiDraft: buildMeetingInsightPromptDraft(
        meeting.title,
        insight,
        translate,
      ),
      aiDraftSourceKey: buildMeetingInsightDraftSourceKey(
        meeting.id,
        insight.id,
      ),
      aiDraftOrigin: 'meeting_insight',
    },
    targetUrlForConversation: (conversationId) =>
      buildMeetingInsightChatTargetUrl(conversationId),
  };
}
