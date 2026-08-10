import { expect, test, type Page } from '@playwright/test';

import { stubConversationsApi, stubShellBackend } from './helpers';

const docsHubItems = [
  {
    id: 'doc-working-notes',
    title: 'Working Notes',
    source_type: 'native_doc',
    source_ref: null,
    source_deeplink: null,
    page_count: 8,
    doc_type: 'general',
    collection: null,
    primary_container: null,
    location_label: 'Workspace Docs',
    is_private: false,
    is_favorite: false,
    can_manage: true,
    can_edit: true,
    can_share: true,
    updated_at: '2026-05-11T00:00:00Z',
    created_at: '2026-05-10T00:00:00Z',
    owner_id: 'user-e2e',
    last_viewed_at: null,
    trashed_at: null,
    sharing_summary: null,
  },
  {
    id: 'doc-bottom-menu',
    title: 'HP ZGX Nano AI Station 셋업',
    source_type: 'native_doc',
    source_ref: null,
    source_deeplink: null,
    page_count: 2,
    doc_type: 'general',
    collection: null,
    primary_container: null,
    location_label: 'Workspace Docs',
    is_private: false,
    is_favorite: false,
    can_manage: true,
    can_edit: true,
    can_share: true,
    updated_at: '2026-05-12T00:00:00Z',
    created_at: '2026-05-10T00:00:00Z',
    owner_id: 'user-e2e',
    last_viewed_at: null,
    trashed_at: null,
    sharing_summary: null,
  },
];

async function stubDocsList(page: Page) {
  await page.route('**/api/v1/workspaces/*/docs/hub**', (route) =>
    route.fulfill({
      json: {
        items: docsHubItems,
        total: docsHubItems.length,
        page: 1,
        page_size: 50,
      },
    }),
  );
  await page.route('**/api/v1/workspaces/*/docs/collections**', (route) =>
    route.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route('**/api/v1/workspaces/*/docs/favorites**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/docs/recent-pages**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/docs/favorites**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/docs/recent-pages**', (route) =>
    route.fulfill({ json: [] }),
  );
}

test.describe('Docs list row menu', () => {
  test('keeps the bottom row menu reachable outside the table frame', async ({ page }) => {
    await stubShellBackend(page);
    await stubConversationsApi(page);
    await stubDocsList(page);

    await page.goto('/w/hq/docs');
    await expect(page.getByText('HP ZGX Nano AI Station 셋업')).toBeVisible();

    await page.locator('tbody tr').last().locator('td').last().locator('button').click();

    const renameAction = page.getByText('이름 변경');
    await expect(renameAction).toBeVisible();
    await expect
      .poll(async () =>
        renameAction.evaluate((node) => {
          const rect = node.getBoundingClientRect();
          const target = document.elementFromPoint(
            rect.left + rect.width / 2,
            rect.top + rect.height / 2,
          );
          return target === node || Boolean(target && (node.contains(target) || target.contains(node)));
        }),
      )
      .toBe(true);
  });
});
