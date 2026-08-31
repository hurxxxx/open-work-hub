import { expect, test, type Page } from '@playwright/test';

import {
  stubConversationsApi,
  stubShellBackend,
  stubWorkspaceAppDataBackend,
} from './helpers';

type DocsFormat = 'block' | 'html';
type DocsHubFormat = DocsFormat | 'mixed';

function docsItem(id: string, title: string, contentFormat: DocsHubFormat) {
  return {
    id,
    title,
    source_type: 'native_doc',
    source_ref: null,
    source_deeplink: null,
    page_count: 1,
    doc_type: 'general',
    content_format: contentFormat,
    collection: null,
    primary_container: null,
    location_label: 'Workspace Docs',
    is_private: false,
    is_favorite: false,
    can_manage: true,
    can_edit: true,
    can_share: true,
    updated_at: '2026-05-18T00:00:00Z',
    created_at: '2026-05-18T00:00:00Z',
    created_by_name: 'E2E Tester',
    owner_id: 'user-e2e',
    last_viewed_at: null,
    trashed_at: null,
    sharing_summary: null,
  };
}

const docsById = {
  'doc-block': docsItem('doc-block', 'Block Format Doc', 'block'),
  'doc-html': docsItem('doc-html', 'HTML Format Doc', 'html'),
  'doc-mixed': docsItem('doc-mixed', 'Mixed Format Doc', 'mixed'),
};

function pageForDoc(
  id: keyof typeof docsById,
  title = docsById[id].title,
  sortOrder = 0,
  pageFormat?: DocsFormat,
) {
  const doc = docsById[id];
  const contentFormat =
    pageFormat ?? (doc.content_format === 'html' ? 'html' : 'block');
  return {
    id: sortOrder === 0 ? `${id}-page` : `${id}-page-${sortOrder + 1}`,
    title,
    source_type: 'native_doc_page',
    source_page_id:
      sortOrder === 0
        ? `${id}-source-page`
        : `${id}-source-page-${sortOrder + 1}`,
    parent_id: null,
    sort_order: sortOrder,
    content_format: contentFormat,
    content_blocks:
      contentFormat === 'block'
        ? [
            {
              type: 'paragraph',
              content: [
                {
                  type: 'text',
                  text: sortOrder === 0 ? 'Block body' : 'Second page body',
                },
              ],
            },
          ]
        : null,
    content_text:
      contentFormat === 'html'
        ? '<!doctype html><html><body><h1>HTML Rendered First</h1><p>Preview body</p></body></html>'
        : null,
    realtime_collab: false,
    can_edit: true,
    created_at: '2026-05-18T00:00:00Z',
    updated_at: '2026-05-18T00:00:00Z',
    trashed_at: null,
  };
}

async function stubDocsContentFormatBackend(page: Page) {
  const pagesByDocId = {
    'doc-block': [
      pageForDoc('doc-block'),
      pageForDoc('doc-block', 'Second Page', 1),
    ],
    'doc-html': [pageForDoc('doc-html')],
    'doc-mixed': [
      pageForDoc('doc-mixed'),
      pageForDoc('doc-mixed', 'HTML Page', 1, 'html'),
    ],
  };

  await page.route('**/api/v1/workspaces/*/docs/hub**', (route) =>
    route.fulfill({
      json: {
        items: Object.values(docsById),
        total: Object.keys(docsById).length,
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
  await page.route('**/api/v1/docs/favorites**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/docs/recent-pages**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/docs/recent-pages**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/docs/shareable-users**', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/workspaces/*/docs/items/*/pages', (route) => {
    const docId =
      route
        .request()
        .url()
        .match(/\/docs\/items\/([^/]+)\/pages/)?.[1] ?? '';
    return route.fulfill({
      json: { items: pagesByDocId[docId as keyof typeof pagesByDocId] ?? [] },
    });
  });
  await page.route('**/api/v1/workspaces/*/docs/items/*/view', (route) =>
    route.fulfill({ json: {} }),
  );
  await page.route('**/api/v1/workspaces/*/docs/items/*', (route) => {
    const docId =
      route
        .request()
        .url()
        .match(/\/docs\/items\/([^/?]+)/)?.[1] ?? '';
    const doc = docsById[docId as keyof typeof docsById];
    return doc
      ? route.fulfill({ json: doc })
      : route.fulfill({ status: 404, json: { detail: 'Not found' } });
  });
  await page.route('**/api/v1/workspaces/*/docs/pages/*', (route) => {
    const pageId =
      route
        .request()
        .url()
        .match(/\/docs\/pages\/([^/?]+)/)?.[1] ?? '';
    const pageItem = Object.values(pagesByDocId)
      .flat()
      .find((item) => item.id === pageId);
    if (pageItem && route.request().method() === 'PATCH') {
      const payload = route.request().postDataJSON() as Partial<
        ReturnType<typeof pageForDoc>
      >;
      Object.assign(pageItem, payload);
    }
    return pageItem
      ? route.fulfill({ json: pageItem })
      : route.fulfill({ status: 404, json: { detail: 'Not found' } });
  });
  await page.route('**/api/v1/workspaces/*/docs/views', (route) =>
    route.fulfill({ json: {} }),
  );
}

test.describe('Docs content formats', () => {
  test.beforeEach(async ({ page }) => {
    await stubWorkspaceAppDataBackend(page);
    await stubShellBackend(page);
    await stubConversationsApi(page);
    await stubDocsContentFormatBackend(page);
  });

  test('shows the document format in the docs list', async ({ page }) => {
    await page.goto('/apps/docs/workspaces/hq');

    await expect(
      page.getByRole('row', { name: /Block Format Doc/ }),
    ).toContainText('블록 에디터');
    await expect(
      page.getByRole('row', { name: /HTML Format Doc/ }),
    ).toContainText('HTML');
    await expect(
      page.getByRole('row', { name: /Mixed Format Doc/ }),
    ).toContainText('혼합');
  });

  test('offers only block and HTML document formats when creating a doc', async ({
    page,
  }) => {
    await page.goto('/apps/docs/workspaces/hq?create=1');

    const dialog = page.getByRole('heading', { name: '새 문서' }).locator('..');

    await expect(
      dialog.getByRole('radio', { name: '블록 에디터' }),
    ).toBeVisible();
    await expect(dialog.getByRole('radio', { name: 'HTML' })).toBeVisible();
    await expect(
      dialog.getByRole('radio', { name: /마크다운|Markdown/ }),
    ).toHaveCount(0);
  });

  test('keeps Markdown actions on block documents without using the Markdown document path', async ({
    page,
  }) => {
    let collabRequested = false;
    await page.route('**/api/v1/workspaces/*/docs/collab/**', (route) => {
      collabRequested = true;
      return route.fulfill({
        status: 500,
        json: { detail: 'unexpected collab request' },
      });
    });

    await page.goto('/apps/docs/workspaces/hq/documents/doc-block');

    await expect(
      page.getByRole('button', { name: '마크다운 내보내기' }),
    ).toBeVisible();
    await expect(page.getByText('마크다운 가져오기')).toBeVisible();
    await expect(page.getByText('마크다운 원문')).toHaveCount(0);
    expect(collabRequested).toBe(false);
  });

  test('imports and exports Markdown through block documents', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const originalCreateObjectURL = URL.createObjectURL.bind(URL);
      URL.createObjectURL = (object: Blob | MediaSource) => {
        if (object instanceof Blob && object.type.includes('text/markdown')) {
          void object.text().then((text) => {
            (
              window as Window & { __lastMarkdownDownload?: string }
            ).__lastMarkdownDownload = text;
          });
        }
        return originalCreateObjectURL(object);
      };
    });
    await page.goto('/apps/docs/workspaces/hq/documents/doc-block');

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '마크다운 내보내기' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe('Block Format Doc.md');
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            (window as Window & { __lastMarkdownDownload?: string })
              .__lastMarkdownDownload ?? '',
        ),
      )
      .toContain('Block body');

    const patchPromise = page.waitForRequest(
      (request) =>
        request.method() === 'PATCH' &&
        request.url().includes('/docs/pages/doc-block-page'),
    );
    await page.locator('input[type="file"]').setInputFiles({
      name: 'import.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from('# Imported title\n\nImported body'),
    });
    await page.getByRole('button', { name: '마크다운 가져오기' }).click();

    const patch = await patchPromise;
    const payload = patch.postDataJSON() as {
      content_blocks?: Array<{ type?: string }>;
    };
    expect(
      payload.content_blocks?.some((block) => block.type === 'heading'),
    ).toBe(true);
    expect(
      payload.content_blocks?.some((block) => block.type === 'paragraph'),
    ).toBe(true);
    await expect(page.getByText('Imported title')).toBeVisible();
    await expect(page.getByText('Imported body')).toBeVisible();
  });

  test('opens editable HTML documents in rendered view before source edit mode', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/apps/docs/workspaces/hq/documents/doc-html');

    const contentCanvasBox = await page
      .getByTestId('docs-content-canvas')
      .boundingBox();
    expect(contentCanvasBox?.width ?? 0).toBeGreaterThan(1200);
    await expect(page.getByText('HTML 미리보기')).toBeVisible();
    await expect(page.locator('textarea')).toHaveCount(0);
    await expect(
      page
        .frameLocator('iframe[title="HTML Format Doc"]')
        .getByText('HTML Rendered First'),
    ).toBeVisible();

    await page.getByRole('button', { name: 'HTML 편집' }).click();
    await expect(page.locator('textarea')).toBeVisible();

    await page.getByRole('button', { name: 'HTML 미리보기' }).click();
    await expect(page.locator('textarea')).toHaveCount(0);
    await expect(
      page
        .frameLocator('iframe[title="HTML Format Doc"]')
        .getByText('Preview body'),
    ).toBeVisible();
  });

  test('opens fullscreen read mode with page navigation and presentation tools', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/apps/docs/workspaces/hq/documents/doc-block');

    await page.getByRole('button', { name: '전체 보기' }).click();
    const dialog = page.getByRole('dialog', { name: '전체 화면 읽기' });

    await expect(dialog).toBeVisible();
    const readModePageBox = await dialog
      .getByTestId('docs-read-mode-page')
      .boundingBox();
    expect(readModePageBox?.width ?? 0).toBeGreaterThan(1450);
    await expect(
      dialog.getByRole('button', { name: /Block Format Doc/ }),
    ).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: /Second Page/ }),
    ).toBeVisible();

    await dialog.getByRole('button', { name: /Second Page/ }).click();
    await expect(
      dialog.getByRole('heading', { level: 1, name: 'Second Page' }),
    ).toBeVisible();
    await expect(dialog.getByText('Second page body')).toBeVisible();

    await dialog.getByRole('button', { name: '레이저' }).click();
    await expect(
      dialog.getByRole('button', { name: '레이저' }),
    ).toHaveAttribute('aria-pressed', 'true');
    const canvasBox = await dialog.locator('canvas').boundingBox();
    if (!canvasBox) {
      throw new Error('Fullscreen read mode canvas was not rendered.');
    }
    await page.mouse.move(canvasBox.x + 120, canvasBox.y + 160);
    await page.mouse.down();
    await page.mouse.move(canvasBox.x + 260, canvasBox.y + 240, { steps: 8 });
    await page.mouse.up();
    await expect(dialog.getByTestId('docs-laser-pointer')).toBeVisible();
    await expect(dialog.getByTestId('docs-laser-pointer')).toHaveCSS(
      'width',
      '8px',
    );
    await expect(dialog.getByTestId('docs-laser-pointer')).toHaveCSS(
      'height',
      '8px',
    );
    await expect(dialog.getByTestId('docs-laser-pointer')).toHaveCSS(
      'box-shadow',
      'none',
    );
    await expect(
      dialog.getByTestId('docs-laser-segment').first(),
    ).toBeVisible();
    await expect(dialog.getByTestId('docs-laser-segment')).toHaveCount(0, {
      timeout: 3000,
    });

    await dialog.getByRole('button', { name: '펜' }).click();
    await expect(dialog.getByRole('button', { name: '펜' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(dialog.locator('canvas')).toBeVisible();
  });

  test('zooms HTML documents in fullscreen read mode', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/apps/docs/workspaces/hq/documents/doc-html');

    await page.getByRole('button', { name: '전체 보기' }).click();
    const dialog = page.getByRole('dialog', { name: '전체 화면 읽기' });
    const zoomSurface = dialog.getByTestId('docs-html-zoom-surface');

    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: 'HTML 확대' }),
    ).toBeVisible();
    await expect(
      dialog.getByRole('button', { name: 'HTML 축소' }),
    ).toBeVisible();
    await expect(dialog.getByTestId('docs-html-zoom-label')).toHaveText('100%');
    await expect(zoomSurface).toHaveAttribute('data-zoom', '1.00');

    await dialog.getByRole('button', { name: 'HTML 확대' }).click();
    await expect(dialog.getByTestId('docs-html-zoom-label')).toHaveText('110%');
    await expect(zoomSurface).toHaveAttribute('data-zoom', '1.10');
    await expect(zoomSurface).toHaveCSS('transform', 'none');
    await expect(
      dialog.locator('iframe[title="HTML Format Doc"]'),
    ).toHaveAttribute('srcdoc', /zoom:1\.10/);

    await dialog.getByRole('button', { name: 'HTML 배율 초기화' }).click();
    await expect(dialog.getByTestId('docs-html-zoom-label')).toHaveText('100%');
    await expect(zoomSurface).toHaveAttribute('data-zoom', '1.00');
  });
});
