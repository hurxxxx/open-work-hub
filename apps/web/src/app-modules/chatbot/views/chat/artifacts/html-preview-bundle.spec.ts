import { afterEach, expect, it, vi } from 'vitest';
import { bundleHtmlPreview, previewPath } from './html-preview-bundle';

vi.mock('esbuild-wasm', async (original) => ({
  ...(await original<typeof import('esbuild-wasm')>()),
  // Node's official API starts its own WASM executable; wasmURL is browser-only.
  initialize: async () => undefined,
}));

afterEach(() => vi.unstubAllGlobals());

it('bundles local module dependencies, cycles, import maps, CSS and images without network', async () => {
  vi.stubGlobal('Uint8Array', new TextEncoder().encode('').constructor);
  const files: Record<string, string> = {
    'demo/lib/a.js':
      "import { b } from './b.js'; export const value = () => b + 1;",
    'demo/lib/b.js':
      "import { value } from './a.js'; export const b = 41; export const cycle = () => value();",
    'demo/main.css':
      "@import './colors.css'; body { background-image: url('./pixel.svg'); }",
    'demo/colors.css': 'body { color: green; }',
    'demo/pixel.svg':
      '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
  };
  const loaded: string[] = [];
  const result = await bundleHtmlPreview(
    `<script type="importmap">{"imports":{"library":"./lib/a.js","helpers/":"./lib/"}}</script>
    <link rel="stylesheet" href="main.css"><img src="pixel.svg">
    <script type="module">import { value } from 'library'; import { cycle } from 'helpers/b.js'; document.body.dataset.result = cycle();</script>`,
    'demo/index.html',
    async (path) => {
      loaded.push(path);
      if (!(path in files)) throw new Error('missing');
      return new TextEncoder().encode(files[path]);
    },
    new AbortController().signal,
  );
  const output = new DOMParser().parseFromString(result, 'text/html');
  expect(output.querySelector('link')).toBeNull();
  expect(output.querySelector('style')?.textContent).toContain('green');
  expect(output.querySelector('img')?.src).toMatch(
    /^data:image\/svg\+xml;base64,/,
  );
  const modules = JSON.parse(
    output.querySelector('script[type="importmap"]')?.textContent || '{}',
  );
  expect(Object.values(modules.imports)).toEqual([
    expect.stringMatching(/^data:text\/javascript;base64,/),
  ]);
  expect(new Set(loaded).size).toBe(5);
});

it('preserves classic-script globals and refuses remote, missing, excessive and aborted input', async () => {
  vi.stubGlobal('Uint8Array', new TextEncoder().encode('').constructor);
  for (const path of [
    'https://cdn.example/a.js',
    '//cdn.example/a.js',
    'file:///etc/passwd',
    'a\\b.js',
    'a\nb.js',
    '%00.js',
  ])
    expect(() => previewPath(path, 'demo/index.html')).toThrow();
  const load = vi.fn(async () =>
    new TextEncoder().encode('var sharedValue = 42;'),
  );
  const result = await bundleHtmlPreview(
    '<script src="a.js"></script>',
    'index.html',
    load,
    new AbortController().signal,
  );
  const classic = new DOMParser()
    .parseFromString(result, 'text/html')
    .querySelector('script');
  expect(atob(classic?.src.split(',')[1] || '')).toBe('var sharedValue = 42;');
  await expect(
    bundleHtmlPreview(
      '<script src="https://cdn.example/a.js"></script>',
      'index.html',
      load,
      new AbortController().signal,
    ),
  ).rejects.toThrow();
  await expect(
    bundleHtmlPreview(
      '<script type="module" src="missing.js"></script>',
      'index.html',
      async () => {
        throw new Error('missing');
      },
      new AbortController().signal,
    ),
  ).rejects.toThrow('missing');
  const abort = new AbortController();
  abort.abort();
  await expect(
    bundleHtmlPreview(
      '<script src="a.js"></script>',
      'index.html',
      load,
      abort.signal,
    ),
  ).rejects.toThrow();
});
