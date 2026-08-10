import { expect, test, type Page, type Route } from '@playwright/test';

import {
  FAKE_PLATFORM_ADMIN_USER,
  stubShellBackend,
  stubWorkspaceAppDataBackend,
} from './helpers';

const CREATED_AT = '2026-06-25T08:00:00.000Z';
const CURRENT_USER_ID = 'user-e2e';
const ACTIVE_CONVERSATION_ID = 'dm-1';

type DmUserFixture = {
  id: string;
  email: string;
  full_name: string;
  display_name: string | null;
};

type DmMessageFixture = {
  id: string;
  conversation_id: string;
  thread_id: string;
  sequence: number;
  sender_id: string;
  sender_name: string;
  read_state: {
    unread_count: number;
    read_by_all: boolean;
  };
  reply_to: null;
  body: string;
  attachments: unknown[];
  created_at: string;
};

function dmUser(index: number): DmUserFixture {
  return {
    id: `dm-user-${index}`,
    email: `dm-user-${index}@example.test`,
    full_name: `DM User ${index}`,
    display_name: `DM User ${index}`,
  };
}

function currentUser(): DmUserFixture {
  return {
    id: CURRENT_USER_ID,
    email: 'e2e@open-work-hub.local',
    full_name: 'E2E Tester',
    display_name: 'E2E Tester',
  };
}

function dmMessage(index: number): DmMessageFixture {
  const own = index % 2 === 0;
  return {
    id: `dm-message-${index}`,
    conversation_id: ACTIVE_CONVERSATION_ID,
    thread_id: ACTIVE_CONVERSATION_ID,
    sequence: index,
    sender_id: own ? CURRENT_USER_ID : 'dm-user-1',
    sender_name: own ? 'E2E Tester' : 'DM User 1',
    read_state: {
      unread_count: 0,
      read_by_all: true,
    },
    reply_to: null,
    body:
      index % 3 === 0
        ? 'Long DM content that should stay in the scrollable message region.'
        : `Message ${index}`,
    attachments: [],
    created_at: CREATED_AT,
  };
}

function dmConversation(index: number) {
  const otherUser = dmUser(index);
  const id = index === 1 ? ACTIVE_CONVERSATION_ID : `dm-${index}`;
  return {
    id,
    conversation_type: 'direct',
    thread_type: 'direct',
    title: null,
    display_name: otherUser.display_name,
    other_user: otherUser,
    participants: [
      {
        user: currentUser(),
        role: 'member',
        joined_at: CREATED_AT,
        left_at: null,
        muted_at: null,
        last_read_message_id: null,
      },
      {
        user: otherUser,
        role: 'member',
        joined_at: CREATED_AT,
        left_at: null,
        muted_at: null,
        last_read_message_id: null,
      },
    ],
    participant_count: 2,
    last_message: dmMessage(index),
    unread_count: 0,
    last_read_message_id: null,
    muted_at: null,
    created_by_id: CURRENT_USER_ID,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
  };
}

async function stubDmLayoutBackend(page: Page): Promise<void> {
  const conversations = Array.from({ length: 18 }, (_, index) =>
    dmConversation(index + 1),
  );
  const activeConversation = conversations[0];
  const messages = Array.from({ length: 24 }, (_, index) =>
    dmMessage(index + 1),
  );

  await page.unroute('**/api/v1/dm/conversations**');
  await page.route('**/api/v1/dm/conversations**', (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (
      request.method() === 'GET' &&
      url.pathname === '/api/v1/dm/conversations'
    ) {
      return route.fulfill({ json: { items: conversations } });
    }
    if (
      request.method() === 'GET' &&
      url.pathname ===
        `/api/v1/dm/conversations/${ACTIVE_CONVERSATION_ID}/messages`
    ) {
      return route.fulfill({ json: { items: messages } });
    }
    if (
      request.method() === 'PATCH' &&
      url.pathname === `/api/v1/dm/conversations/${ACTIVE_CONVERSATION_ID}/read`
    ) {
      return route.fulfill({ json: activeConversation });
    }
    return route.fulfill({
      status: 404,
      json: {
        detail: `Unhandled DM E2E route: ${request.method()} ${url.pathname}`,
      },
    });
  });
}

test('keeps the floating DM composer inside the widget viewport', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1770, height: 856 });
  await stubWorkspaceAppDataBackend(page);
  await stubShellBackend(page, { user: FAKE_PLATFORM_ADMIN_USER });
  await stubDmLayoutBackend(page);

  await page.goto('/admin/general');
  await expect(
    page.getByRole('navigation', { name: '전역 위젯 도크' }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'DM' })).toBeVisible();

  await page.evaluate((threadId) => {
    window.dispatchEvent(
      new CustomEvent('open-work-hub:floating-dm-open', {
        detail: { threadId },
      }),
    );
  }, ACTIVE_CONVERSATION_ID);

  const composer = page.locator('textarea[aria-label="메시지 입력"]');
  await expect(composer).toBeVisible();

  const metrics = await composer.evaluate((textarea) => {
    const panel = textarea.closest('aside[aria-label]');
    const footer = textarea.closest('footer');
    if (!panel || !footer) {
      throw new Error('Floating DM layout elements were not found.');
    }
    const panelRect = panel.getBoundingClientRect();
    const footerRect = footer.getBoundingClientRect();
    const textareaRect = textarea.getBoundingClientRect();
    return {
      footerBottom: footerRect.bottom,
      panelBottom: panelRect.bottom,
      panelTop: panelRect.top,
      textareaBottom: textareaRect.bottom,
    };
  });

  expect(metrics.footerBottom).toBeLessThanOrEqual(metrics.panelBottom + 1);
  expect(metrics.textareaBottom).toBeLessThanOrEqual(metrics.panelBottom + 1);
  expect(metrics.footerBottom).toBeGreaterThan(metrics.panelTop);
});
