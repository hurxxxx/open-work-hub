import { expect, test, type Page } from '@playwright/test';

async function openPreview(
  page: Page,
  content: string,
  files: Record<string, string> = {},
) {
  await page.route('**/preview-fixture', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<!doctype html><title>Preview fixture</title>',
    }),
  );
  await page.goto('/preview-fixture');
  await page.evaluate(
    async ({ content, files }) => {
      const modulePath =
        '/src/app-modules/chatbot/views/chat/artifacts/html-preview-bundle.ts';
      const policyPath =
        '/src/app-modules/chatbot/views/chat/artifacts/html-preview-policy.ts';
      const { bundleHtmlPreview } = await import(modulePath);
      const { HTML_PREVIEW_CSP } = await import(policyPath);
      const html = await bundleHtmlPreview(
        content,
        'demo/index.html',
        async (path: string) => {
          if (!(path in files))
            throw new Error('Unexpected fixture dependency');
          return new TextEncoder().encode(files[path]);
        },
        new AbortController().signal,
      );
      const frame = document.createElement('iframe');
      frame.title = 'Saved result';
      frame.setAttribute('sandbox', 'allow-scripts');
      frame.srcdoc = `<meta http-equiv="Content-Security-Policy" content="${HTML_PREVIEW_CSP}">${html}`;
      document.body.appendChild(frame);
    },
    { content, files },
  );
}

test('saved deferred classic scripts retain globals and ordering after document parsing', async ({
  page,
}) => {
  await openPreview(
    page,
    `<head><script defer src="first.js"></script>
    <script type="module">window.sequence.push('module');</script>
    <script defer src="second.js"></script></head><body><p id="result">pending</p></body>`,
    {
      'demo/first.js':
        "var sharedValue=41;window.sequence=['first'];document.querySelector('#result').textContent=sharedValue;",
      'demo/second.js':
        "window.sequence.push('second');document.querySelector('#result').textContent=JSON.stringify({value:sharedValue+1,order:window.sequence});",
    },
  );
  await expect(page.frameLocator('iframe').locator('#result')).toHaveText(
    JSON.stringify({ value: 42, order: ['first', 'module', 'second'] }),
  );
});

test('top-level await, cycles and repeated module entries share one module instance', async ({
  page,
}) => {
  await openPreview(
    page,
    `<head><script type="module" src="first.js"></script>
    <script type="module">import './first.js'; import {snapshot} from './shared.js';
    document.querySelector('#result').textContent=JSON.stringify({value:snapshot(),initializations:window.initializations});</script>
    <script type="module" src="first.js"></script></head><body><p id="result">pending</p></body>`,
    {
      'demo/shared.js':
        "import {read} from './cycle.js'; window.initializations=(window.initializations||0)+1; export let value=0; export const bump=()=>++value; export const snapshot=()=>read();",
      'demo/cycle.js':
        "import {value} from './shared.js'; export const read=()=>value;",
      'demo/first.js':
        "import {bump} from './shared.js'; await Promise.resolve(); document.body.dataset.count=String(bump());",
    },
  );
  const frame = page.frameLocator('iframe');
  await expect(frame.locator('#result')).toHaveText(
    JSON.stringify({ value: 1, initializations: 1 }),
  );
  await expect(frame.locator('body')).toHaveAttribute('data-count', '1');
});

test('embedded scripts cannot access the parent or send network requests', async ({
  page,
}) => {
  const network: string[] = [];
  await page.route('https://external.invalid/**', (route) => {
    network.push(route.request().url());
    return route.abort();
  });
  await openPreview(
    page,
    `<body><p id="result">pending</p><script>
    let blocked=false;try{parent.document.body.dataset.escaped='yes'}catch{blocked=true}
    fetch('https://external.invalid/private').catch(()=>document.querySelector('#result').textContent=String(blocked));
    </script></body>`,
  );
  await expect(page.frameLocator('iframe').locator('#result')).toHaveText(
    'true',
  );
  expect(network).toEqual([]);
  await expect(page.locator('body')).not.toHaveAttribute('data-escaped');
});
