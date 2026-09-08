import type { NavigateFunction } from 'react-router-dom';

import { createConversation } from '@/src/app-modules/chatbot/public-api';
import { i18n } from '@/src/platform/i18n';
import type { MeetingDetail } from '../../api/meeting-api';
import type { MeetingInsightItem } from '../../api/meeting-insights-api';
import {
  buildMeetingInsightPromptDraft,
  extractMeetingInsightTitle,
  planMeetingInsightChatHandoff,
  type MeetingInsightChatTranslator,
} from './meeting-insight-chat-handoff';

export interface OpenMeetingInsightInChatArgs {
  navigate: NavigateFunction;
  token: string;

  meeting: Pick<MeetingDetail, 'id' | 'title'>;
  insight: MeetingInsightItem;
}

const translateMeetingInsightChatPrompt: MeetingInsightChatTranslator = (
  key,
  variables,
) => i18n.t(key, variables);

/**
 * Navigate to the AI view with a pre-filled draft sourced from a
 * meeting insight. Step F semantics: create an empty meeting-scoped
 * conversation first, then hand the draft to ChatbotView through router
 * state so the first submitted turn already runs inside that scope.
 */
export async function openMeetingInsightInChat({
  navigate,
  token,
  meeting,
  insight,
}: OpenMeetingInsightInChatArgs): Promise<void> {
  const handoffPlan = planMeetingInsightChatHandoff({
    meeting,
    insight,
    translate: translateMeetingInsightChatPrompt,
  });
  const conversation = await createConversation(
    token,
    handoffPlan.conversationRequest,
  );
  navigate(handoffPlan.targetUrlForConversation(conversation.id), {
    state: handoffPlan.locationState,
  });
}

// Exported for unit tests that want to verify the generated URL shape
// without depending on a router fixture.
export const __test = {
  extractInsightTitle: extractMeetingInsightTitle,
  buildPromptDraft: (meetingTitle: string, insight: MeetingInsightItem) =>
    buildMeetingInsightPromptDraft(
      meetingTitle,
      insight,
      translateMeetingInsightChatPrompt,
    ),
};
