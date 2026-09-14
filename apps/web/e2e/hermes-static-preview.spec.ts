import { expect, test } from '@playwright/test';

test('saved deferred classic scripts retain globals and ordering after document parsing', async ({
  page,
}) => {
  await page.route('**/preview-fixture', (route) =>
    route.fulfill({
      contentType: 'text/html',
      body: '<!doctype html><title>Preview fixture</title>',
    }),
  );
  await page.goto('/preview-fixture');
  await page.evaluate(async () => {
    const modulePath =
      '/src/app-modules/chatbot/views/chat/artifacts/html-preview-bundle.ts';
    const { bundleHtmlPreview } = await import(modulePath);
    const files: Record<string, string> = {
      'demo/first.js':
        "var sharedValue=41;window.sequence=['first'];document.querySelector('#result').textContent=sharedValue;",
      'demo/second.js':
        "window.sequence.push('second');document.querySelector('#result').textContent=JSON.stringify({value:sharedValue+1,order:window.sequence});",
    };
    const content = `<head><script defer src="first.js"></script>
      <script type="module">window.sequence.push('module');</script>
      <script defer src="second.js"></script></head><body><p id="result">pending</p></body>`;
    const html = await bundleHtmlPreview(
      content,
      'demo/index.html',
      async (path: string) => {
        if (!(path in files)) throw new Error('Unexpected fixture dependency');
        return new TextEncoder().encode(files[path]);
      },
      new AbortController().signal,
    );
    const frame = document.createElement('iframe');
    frame.title = 'Saved result';
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.srcdoc = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; connect-src 'none'">${html}`;
    document.body.appendChild(frame);
  });
  await expect(page.frameLocator('iframe').locator('#result')).toHaveText(
    JSON.stringify({ value: 42, order: ['first', 'module', 'second'] }),
  );
});
