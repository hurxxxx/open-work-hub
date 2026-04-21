import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AiApiError } from '@/src/domains/ai/ai-api';
import type { MeetingDetail } from '@/src/domains/meeting/meeting-api';
import type {
  MeetingFollowupResult,
  MeetingInsightItem,
  MeetingInsightListResult,
} from '@/src/domains/meeting/meeting-insights-api';

import { MeetingInsightSection } from './MeetingInsightSection';

const insightsHarness = vi.hoisted(() => ({
  extractActions: vi.fn(),
  extractDecisions: vi.fn(),
  draftFollowupSchedule: vi.fn(),
}));

vi.mock('@/src/domains/meeting/meeting-insights-api', async () => {
  const actual = await vi.importActual<
    typeof import('@/src/domains/meeting/meeting-insights-api')
  >('@/src/domains/meeting/meeting-insights-api');
  return {
    ...actual,
    extractActions: insightsHarness.extractActions,
    extractDecisions: insightsHarness.extractDecisions,
    draftFollowupSchedule: insightsHarness.draftFollowupSchedule,
  };
});

function insightItem(
  overrides: Partial<MeetingInsightItem> & Pick<MeetingInsightItem, 'id' | 'insight_type' | 'payload'>,
): MeetingInsightItem {
  return {
    meeting_id: 'meeting-1',
    recording_id: null,
    workspace_id: 'workspace-1',
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

function baseMeeting(
  overrides: Partial<MeetingDetail> = {},
): MeetingDetail {
  return {
    id: 'meeting-1',
    workspace_id: 'workspace-1',
    organizer_id: 'user-organizer',
    organizer_name: 'Organizer',
    notes_doc_id: null,
    notes_page_id: null,
    title: 'Weekly Sync',
    agenda: '',
    start_at: '2026-04-21T00:00:00',
    end_at: '2026-04-21T01:00:00',
    status: 'scheduled',
    attendees: [],
    task_links: [],
    doc_links: [],
    file_attachments: [],
    recordings: [
      {
        id: 'rec-1',
        meeting_id: 'meeting-1',
        uploaded_by_id: 'user-organizer',
        storage_key: 'k',
        duration_sec: 120,
        source: 'manual_upload',
        transcription_status: 'done',
        progress_pct: 100,
        file_size: 1024,
        mime_type: 'audio/webm',
        failure_reason: null,
        linked_doc_id: null,
        linked_task_id: null,
        transcribe_started_at: null,
        transcribe_completed_at: null,
        created_at: '2026-04-21T00:00:00',
      },
    ],
    active_recording_lock: null,
    created_at: '2026-04-21T00:00:00',
    updated_at: '2026-04-21T00:00:00',
    ...overrides,
  };
}

async function expectAllToolsCalled() {
  await waitFor(() => {
    expect(insightsHarness.extractActions).toHaveBeenCalled();
    expect(insightsHarness.extractDecisions).toHaveBeenCalled();
    expect(insightsHarness.draftFollowupSchedule).toHaveBeenCalled();
  });
}

describe('MeetingInsightSection', () => {
  beforeEach(() => {
    insightsHarness.extractActions.mockReset();
    insightsHarness.extractDecisions.mockReset();
    insightsHarness.draftFollowupSchedule.mockReset();
  });

  it('renders items from all three groups on initial load', async () => {
    insightsHarness.extractActions.mockResolvedValue({
      items: [
        insightItem({
          id: 'a-1',
          insight_type: 'action',
          payload: { title: '로그인 플로우 정리' },
        }),
      ],
    } satisfies MeetingInsightListResult);
    insightsHarness.extractDecisions.mockResolvedValue({
      items: [
        insightItem({
          id: 'd-1',
          insight_type: 'decision',
          payload: { statement: '신규 인증 흐름 채택' },
        }),
      ],
    } satisfies MeetingInsightListResult);
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [
        insightItem({
          id: 'f-1',
          insight_type: 'followup_schedule',
          payload: {
            proposed_title: '후속 점검 회의',
            duration_minutes: 30,
            proposed_slots: [],
          },
        }),
      ],
      attendee_user_ids: [],
      availability: null,
    } satisfies MeetingFollowupResult);

    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await screen.findByText('로그인 플로우 정리');
    expect(screen.getByText('신규 인증 흐름 채택')).toBeTruthy();
    expect(screen.getByText('후속 점검 회의')).toBeTruthy();
  });

  it('renders successful groups even when one tool rejects (Promise.allSettled)', async () => {
    insightsHarness.extractActions.mockResolvedValue({
      items: [
        insightItem({
          id: 'a-1',
          insight_type: 'action',
          payload: { title: 'Action-A' },
        }),
      ],
    });
    insightsHarness.extractDecisions.mockRejectedValue(new Error('decisions-failed'));
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await screen.findByText('Action-A');
    expect(screen.getByText('decisions-failed')).toBeTruthy();
  });

  it('converts AiApiError with status 409 to a summary-not-ready hint', async () => {
    insightsHarness.extractActions.mockRejectedValue(
      new AiApiError(409, 'Meeting recording summary is not available yet.'),
    );
    insightsHarness.extractDecisions.mockResolvedValue({ items: [] });
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await screen.findByText('회의 요약이 아직 없어 AI 제안을 다시 만들 수 없습니다.');
  });

  it('shows empty placeholder when all groups return zero items', async () => {
    insightsHarness.extractActions.mockResolvedValue({ items: [] });
    insightsHarness.extractDecisions.mockResolvedValue({ items: [] });
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await expectAllToolsCalled();
    await screen.findByText('이 회의에서 발견된 AI 제안이 없습니다.');
  });

  it('calls refresh=true in sequence when 재추출 is clicked', async () => {
    const callOrder: string[] = [];
    insightsHarness.extractActions.mockImplementation((_t, _id, opts) => {
      if (opts?.refresh) callOrder.push('actions');
      return Promise.resolve({ items: [] });
    });
    insightsHarness.extractDecisions.mockImplementation((_t, _id, opts) => {
      if (opts?.refresh) callOrder.push('decisions');
      return Promise.resolve({ items: [] });
    });
    insightsHarness.draftFollowupSchedule.mockImplementation((_t, _id, opts) => {
      if (opts?.refresh) callOrder.push('followup');
      return Promise.resolve({
        items: [],
        attendee_user_ids: [],
        availability: null,
      });
    });

    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await expectAllToolsCalled();

    fireEvent.click(screen.getByRole('button', { name: /재추출/ }));

    await waitFor(() => {
      expect(callOrder).toEqual(['actions', 'decisions', 'followup']);
    });
  });

  it('invokes onOpenInChat with the raw insight when 챗에서 진행 is clicked', async () => {
    const actionItem = insightItem({
      id: 'a-1',
      insight_type: 'action',
      payload: { title: 'Click me' },
    });
    insightsHarness.extractActions.mockResolvedValue({ items: [actionItem] });
    insightsHarness.extractDecisions.mockResolvedValue({ items: [] });
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    const onOpenInChat = vi.fn();
    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={onOpenInChat}
      />,
    );

    await screen.findByText('Click me');
    fireEvent.click(screen.getByRole('button', { name: '챗에서 진행' }));
    await waitFor(() => {
      expect(onOpenInChat).toHaveBeenCalledWith(actionItem);
    });
  });

  it('shows the inline openError and keeps other cards enabled when onOpenInChat rejects', async () => {
    const actionItem = insightItem({
      id: 'a-1',
      insight_type: 'action',
      payload: { title: '첫째' },
    });
    const secondAction = insightItem({
      id: 'a-2',
      insight_type: 'action',
      payload: { title: '둘째' },
    });
    insightsHarness.extractActions.mockResolvedValue({
      items: [actionItem, secondAction],
    });
    insightsHarness.extractDecisions.mockResolvedValue({ items: [] });
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    const onOpenInChat = vi.fn().mockRejectedValue(new Error('conversation down'));
    render(
      <MeetingInsightSection
        meeting={baseMeeting()}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={onOpenInChat}
      />,
    );

    await screen.findByText('첫째');
    const buttons = screen.getAllByRole('button', { name: '챗에서 진행' });
    fireEvent.click(buttons[0]!);
    await screen.findByText('conversation down');
    // After rejection settles, openingInsightId clears and the other
    // button becomes clickable again.
    await waitFor(() => {
      for (const button of screen.getAllByRole('button', { name: '챗에서 진행' })) {
        expect((button as HTMLButtonElement).disabled).toBe(false);
      }
    });
  });

  it('preserves previously rendered items when an auto-refetch rejects', async () => {
    // Auto-refetch is triggered by recording status transitions and
    // must not wipe cards that were already visible on a transient
    // per-tool failure — the user would lose their context. Only
    // fulfilled branches replace items; rejected branches keep the
    // prior snapshot and surface an inline warning.
    const firstAction = insightItem({
      id: 'a-1',
      insight_type: 'action',
      payload: { title: '유지되어야 하는 액션' },
    });
    insightsHarness.extractActions
      .mockResolvedValueOnce({ items: [firstAction] })
      .mockRejectedValueOnce(new Error('actions-down'));
    insightsHarness.extractDecisions.mockResolvedValue({ items: [] });
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    const initialMeeting = baseMeeting();
    const { rerender } = render(
      <MeetingInsightSection
        meeting={initialMeeting}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await screen.findByText('유지되어야 하는 액션');

    // Simulate a recording status transition — triggers the auto-
    // refetch effect via the recording signature dep.
    const updatedMeeting = baseMeeting({
      recordings: [
        {
          ...initialMeeting.recordings[0]!,
          transcription_status: 'extracting_insights',
          progress_pct: 90,
        },
      ],
    });
    rerender(
      <MeetingInsightSection
        meeting={updatedMeeting}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await screen.findByText('actions-down');
    // The existing card should still be rendered despite the refetch
    // failure — preservation guarantee.
    expect(screen.getByText('유지되어야 하는 액션')).toBeTruthy();
  });

  it('disables 재추출 when no recording is done', async () => {
    insightsHarness.extractActions.mockResolvedValue({ items: [] });
    insightsHarness.extractDecisions.mockResolvedValue({ items: [] });
    insightsHarness.draftFollowupSchedule.mockResolvedValue({
      items: [],
      attendee_user_ids: [],
      availability: null,
    });

    const meeting = baseMeeting({
      recordings: [
        {
          ...baseMeeting().recordings[0]!,
          transcription_status: 'extracting_insights',
          progress_pct: 90,
        },
      ],
    });

    render(
      <MeetingInsightSection
        meeting={meeting}
        workspaceSlug="hq"
        token="test-token"
        onOpenInChat={vi.fn()}
      />,
    );

    await expectAllToolsCalled();
    const button = screen.getByRole('button', { name: /재추출/ });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('AI 제안을 생성 중입니다.')).toBeTruthy();
  });
});
