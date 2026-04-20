import { expect, test } from '@playwright/test';
import type { Route } from '@playwright/test';

import { stubConversationsApi, stubShellBackend } from './helpers';

function sseFrame(type: string, seq: number, data: unknown): string {
  const payload = JSON.stringify({ seq, timestamp_ms: 0, type, data });
  return `event: ${type}\r\ndata: ${payload}\r\n\r\n`;
}

/**
 * Canned SSE body that exercises the full artifact lifecycle:
 *   conversation_attached → content_delta → artifact_started →
 *   artifact_delta × 2 → artifact_completed → content_delta → done.
 */
const ARTIFACT_STREAM_BODY = [
  sseFrame('conversation_attached', 0, { conversation_id: 'stub-conversation' }),
  sseFrame('content_delta', 1, { text: '요청하신 초안을 열었습니다. ' }),
  sseFrame('artifact_started', 2, {
    artifact_id: 'art-42',
    artifact_type: 'document',
    title: '보고서 초안',
  }),
  sseFrame('artifact_delta', 3, {
    artifact_id: 'art-42',
    delta: '# 보고서 초안\n\n',
  }),
  sseFrame('artifact_delta', 4, {
    artifact_id: 'art-42',
    delta: '1. 요약: 내용 요약입니다.\n2. 다음 단계: 이행합니다.',
  }),
  sseFrame('artifact_completed', 5, { artifact_id: 'art-42' }),
  sseFrame('content_delta', 6, { text: '오른쪽 패널에서 확인하세요.' }),
  sseFrame('done', 7, {
    finish_reason: 'stop',
    audit_id: null,
    meta: {
      policy: 'local_only',
      chosen_pool: 'local',
      decision_reason: 'policy_local_only',
      forced_local: false,
      pii_hits: [],
      model: 'test-model',
      chosen_model: 'test-model',
      canonical_model: 'test-model',
      provider: 'mlx-lm',
    },
  }),
].join('');

async function stubArtifactStream(page: import('@playwright/test').Page) {
  await page.route('**/ai/chat/stream', (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: ARTIFACT_STREAM_BODY,
    }),
  );
}

test.describe('AI chat artifacts', () => {
  test.beforeEach(async ({ page }) => {
    await stubShellBackend(page);
    await stubConversationsApi(page);
  });

  test('submitting a prompt that produces an artifact opens the side panel', async ({
    page,
  }) => {
    await stubArtifactStream(page);
    await page.goto('/w/hq/ai');

    const composer = page.getByPlaceholder('메시지를 입력하세요');
    await composer.fill('보고서 초안 만들어줘');
    await composer.press('Enter');

    // Artifact card lands inline in the thread.
    await expect(page.getByTestId('artifact-card-art-42')).toBeVisible();

    // Side panel auto-opens with the artifact title + rendered markdown.
    const panel = page.getByRole('dialog', { name: '보고서 초안' });
    await expect(panel).toBeVisible();
    // Panel header h2 + markdown h1 both say "보고서 초안"; check the
    // markdown-rendered list item that's unique to the body content.
    await expect(panel.getByText(/요약/)).toBeVisible();

    // URL now carries `?a=<id>` so a refresh would reopen the same artifact.
    await expect(page).toHaveURL(/[?&]a=art-42(&|$)/);
  });

  test('closing the panel clears `?a=`; clicking the card reopens it', async ({
    page,
  }) => {
    await stubArtifactStream(page);
    await page.goto('/w/hq/ai');

    await page.getByPlaceholder('메시지를 입력하세요').fill('보고서');
    await page.getByPlaceholder('메시지를 입력하세요').press('Enter');

    const card = page.getByTestId('artifact-card-art-42');
    await expect(card).toBeVisible();

    // Auto-opened once — close it.
    await page.getByRole('button', { name: '패널 닫기' }).click();
    await expect(page).not.toHaveURL(/[?&]a=/);

    // Clicking the inline card re-opens the panel and writes `?a=` back.
    await card.click();
    await expect(page.getByRole('dialog', { name: '보고서 초안' })).toBeVisible();
    await expect(page).toHaveURL(/[?&]a=art-42(&|$)/);
  });

  test('reloading a persisted conversation with an artifact restores the panel state', async ({
    page,
  }) => {
    // Replace the default conversations stub with one that has a saved
    // artifact on the assistant turn so we test the hydrate path.
    await stubConversationsApi(page, {
      list: [
        {
          id: 'c-archived',
          title: '이전 대화',
          createdAt: '2026-04-19T00:00:00',
          updatedAt: '2026-04-19T00:05:00',
        },
      ],
      detail: {
        'c-archived': {
          id: 'c-archived',
          title: '이전 대화',
          createdAt: '2026-04-19T00:00:00',
          updatedAt: '2026-04-19T00:05:00',
          turns: [
            {
              id: 't-user',
              seq: 0,
              role: 'user',
              content: '보고서 초안',
              createdAt: '2026-04-19T00:00:10',
            },
            {
              id: 't-assistant',
              seq: 1,
              role: 'assistant',
              content: '초안을 저장했습니다.',
              createdAt: '2026-04-19T00:00:30',
              // Server flattens meta.artifacts onto the turn out shape.
              artifacts: [
                {
                  id: 'saved-42',
                  type: 'document',
                  title: '저장된 초안',
                  content: '# 저장된 초안\n\n이전에 생성된 본문.',
                  status: 'closed',
                },
              ],
            } as Record<string, unknown>,
          ],
        },
      },
    });

    await page.goto('/w/hq/ai?c=c-archived&a=saved-42');

    // Inline card is present on the assistant turn…
    await expect(page.getByTestId('artifact-card-saved-42')).toBeVisible();
    // …and the side panel shows the persisted body rendered as markdown.
    const panel = page.getByRole('dialog', { name: '저장된 초안' });
    await expect(panel).toBeVisible();
    await expect(panel.getByText('이전에 생성된 본문.')).toBeVisible();
  });
});
