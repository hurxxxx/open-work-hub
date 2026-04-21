import { expect, test } from '@playwright/test';

import {
  stubConversationsApi,
  stubMeetingDetail,
  stubMeetingInsights,
  stubShellBackend,
} from './helpers';

const MEETING_ID = 'meeting-scope-1';

const MEETING_DETAIL = {
  id: MEETING_ID,
  workspace_id: 'workspace-hq',
  organizer_id: 'user-e2e',
  organizer_name: 'E2E Tester',
  notes_doc_id: 'doc-meeting-1',
  notes_page_id: 'page-meeting-1',
  title: '주간 운영 점검',
  agenda: '액션 아이템 점검',
  start_at: '2026-04-22T01:00:00',
  end_at: '2026-04-22T02:00:00',
  status: 'completed',
  attendees: [
    {
      id: 'attendee-1',
      user_id: 'user-e2e',
      email: 'e2e@aidoo.local',
      full_name: 'E2E Tester',
      role: 'required',
      response: 'accepted',
    },
  ],
  task_links: [],
  doc_links: [],
  file_attachments: [],
  recordings: [
    {
      id: 'recording-1',
      meeting_id: MEETING_ID,
      uploaded_by_id: 'user-e2e',
      storage_key: 'recordings/meeting-scope-1.wav',
      duration_sec: 120,
      source: 'upload',
      transcription_status: 'done',
      progress_pct: 100,
      file_size: 1024,
      mime_type: 'audio/wav',
      failure_reason: null,
      linked_doc_id: null,
      linked_task_id: null,
      transcribe_started_at: '2026-04-22T01:00:00',
      transcribe_completed_at: '2026-04-22T01:05:00',
      created_at: '2026-04-22T01:00:00',
    },
  ],
  active_recording_lock: null,
  created_at: '2026-04-22T00:55:00',
  updated_at: '2026-04-22T01:05:00',
};

test.describe('Meeting detail -> scoped AI entry', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
    await stubMeetingDetail(page, MEETING_DETAIL);
    await page.route('**/docs/items/doc-meeting-1', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        json: {
          id: 'doc-meeting-1',
          source_app: 'meeting',
          source_type: 'native_doc',
          source_id: 'doc-meeting-1',
          source_kind: 'meeting_notes',
          source_ref: null,
          generation_kind: 'human',
          structure_kind: 'page_tree',
          location_label: 'Meeting',
          container_label: '회의 메모',
          primary_container: null,
          source_badge: 'Meeting',
          source_deeplink: null,
          title: '주간 운영 점검 메모',
          page_count: 1,
          created_by_id: 'user-e2e',
          created_by_name: 'E2E Tester',
          created_at: '2026-04-22T00:55:00Z',
          updated_at: '2026-04-22T01:05:00Z',
          trashed_at: null,
          is_favorite: false,
          is_private: true,
          last_viewed_at: null,
          can_view: true,
          can_edit: false,
          can_share: false,
          can_manage: false,
          sharing_summary: null,
        },
      });
    });
    await page.route('**/docs/items/doc-meeting-1/pages', async (route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      await route.fulfill({
        json: {
          items: [
            {
              id: 'page-meeting-1',
              doc_id: 'doc-meeting-1',
              source_type: 'native_doc_page',
              source_page_id: 'page-meeting-1',
              parent_id: null,
              title: '주간 운영 점검 메모',
              content_blocks: [],
              sort_order: 0,
              created_by_id: 'user-e2e',
              created_by_name: 'E2E Tester',
              created_at: '2026-04-22T00:55:00Z',
              updated_at: '2026-04-22T01:05:00Z',
              trashed_at: null,
              can_edit: false,
              realtime_collab: false,
            },
          ],
        },
      });
    });
    await page.route('**/docs/items/doc-meeting-1/view', async (route) => {
      await route.fulfill({ status: 204, body: '' });
    });
    await stubMeetingInsights(page, {
      actions: {
        items: [
          {
            id: 'insight-action-1',
            meeting_id: MEETING_ID,
            recording_id: 'recording-1',
            workspace_id: 'workspace-hq',
            insight_type: 'action',
            payload: {
              title: '로그인 플로우 정리',
              description: '다음 배포 전까지 로그인 플로우를 정리한다.',
              proposed_due_date: '2026-04-25',
            },
            confidence: 0.92,
            source_span: null,
            status: 'draft',
            accepted_as_kind: null,
            accepted_as_id: null,
            created_by_run_id: 'playwright-meeting-scope',
            created_at: '2026-04-22T01:05:00',
          },
        ],
      },
      decisions: { items: [] },
      followup: { items: [], attendee_user_ids: [], availability: null },
    });
    await stubConversationsApi(page, {
      createResponse: {
        id: 'meeting-conversation-1',
        title: '',
        createdAt: '2026-04-22T01:10:00Z',
        updatedAt: '2026-04-22T01:10:00Z',
        scopeRef: 'meeting',
        scopeResourceId: MEETING_ID,
        livePendingApproval: null,
        turns: [],
      },
      detail: {
        'meeting-conversation-1': {
          id: 'meeting-conversation-1',
          title: '',
          createdAt: '2026-04-22T01:10:00Z',
          updatedAt: '2026-04-22T01:10:00Z',
          scopeRef: 'meeting',
          scopeResourceId: MEETING_ID,
          livePendingApproval: null,
          turns: [],
        },
      },
    });
  });

  test('creates a meeting-scoped conversation and carries the draft into AIView', async ({
    page,
  }) => {
    await page.goto(`/w/hq/meeting/${MEETING_ID}`);

    await expect(page.getByText('AI 제안')).toBeVisible();
    await expect(page.getByText('로그인 플로우 정리')).toBeVisible();

    await page.getByRole('button', { name: '챗에서 진행' }).click();

    await expect(page).toHaveURL(/\/w\/hq\/ai\?c=meeting-conversation-1$/);
    await expect(page.getByTestId('ai-scope-chip')).toBeVisible();
    await expect(page.getByPlaceholder('메시지를 입력하세요')).toHaveValue(
      /로그인 플로우 정리/,
    );
  });
});
