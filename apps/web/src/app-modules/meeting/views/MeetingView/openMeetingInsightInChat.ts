import type { NavigateFunction } from 'react-router-dom';

import { createConversation } from '@/src/domains/ai/conversations-api';
import type { MeetingDetail } from '@/src/domains/meeting/meeting-api';
import type { MeetingInsightItem } from '@/src/domains/meeting/meeting-insights-api';
import { buildWorkspaceAppPath } from '@/src/domains/workspaces/workspace-utils';

/**
 * Pull the primary title/label out of a raw ``MeetingInsightItem``.
 * Payload shape is type-dependent (see backend ``_serialize_insight``),
 * so we branch on ``insight_type`` rather than trusting flat keys on
 * the outer record.
 */
function extractInsightTitle(insight: MeetingInsightItem): string {
  const payload = insight.payload;
  const read = (key: string): string => {
    const value = payload[key];
    return typeof value === 'string' ? value : '';
  };
  switch (insight.insight_type) {
    case 'action':
      return read('title');
    case 'decision':
      return read('statement');
    case 'followup_schedule':
      return read('proposed_title');
    default:
      return '';
  }
}

function buildPromptDraft(
  meetingTitle: string,
  insight: MeetingInsightItem,
): string {
  const label = extractInsightTitle(insight);
  switch (insight.insight_type) {
    case 'action':
      return `회의 \`${meetingTitle}\`의 액션 아이템 \`${label}\`을(를) PMS 이슈로 만들고 싶어. 필요하면 회의 제안을 다시 확인한 뒤 승인 가능한 형태로 정리해줘.`;
    case 'decision':
      return `회의 \`${meetingTitle}\`의 결정사항 \`${label}\`를 바탕으로 후속 문서나 필요한 작업을 제안해줘.`;
    case 'followup_schedule':
      return `회의 \`${meetingTitle}\`의 후속 회의 제안 \`${label}\`을(를) 일정으로 만들 수 있게 정리해줘.`;
    default:
      return '';
  }
}

export interface OpenMeetingInsightInChatArgs {
  navigate: NavigateFunction;
  token: string;
  workspaceSlug: string;
  meeting: Pick<MeetingDetail, 'id' | 'title'>;
  insight: MeetingInsightItem;
}

interface MeetingInsightDraftLocationState {
  aiDraft: string;
  aiDraftSourceKey: string;
  aiDraftOrigin: 'meeting_insight';
}

/**
 * Navigate to the AI view with a pre-filled draft sourced from a
 * meeting insight. Step F semantics: create an empty meeting-scoped
 * conversation first, then hand the draft to AIView through router
 * state so the first submitted turn already runs inside that scope.
 */
export async function openMeetingInsightInChat({
  navigate,
  token,
  workspaceSlug,
  meeting,
  insight,
}: OpenMeetingInsightInChatArgs): Promise<void> {
  const draft = buildPromptDraft(meeting.title, insight);
  const conversation = await createConversation(token, {
    scopeRef: 'meeting',
    scopeResourceId: meeting.id,
  });
  navigate(
    buildWorkspaceAppPath(
      workspaceSlug,
      'ai',
      `?c=${encodeURIComponent(conversation.id)}`,
    ),
    {
      state: {
        aiDraft: draft,
        aiDraftSourceKey: `meeting-insight:${meeting.id}:${insight.id}`,
        aiDraftOrigin: 'meeting_insight',
      } satisfies MeetingInsightDraftLocationState,
    },
  );
}

// Exported for unit tests that want to verify the generated URL shape
// without depending on a router fixture.
export const __test = { extractInsightTitle, buildPromptDraft };
