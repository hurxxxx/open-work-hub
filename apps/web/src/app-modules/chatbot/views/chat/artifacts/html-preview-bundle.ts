import { i18n } from '@/src/platform/i18n';
import type { Loader } from 'esbuild-wasm';
import wasmURL from 'esbuild-wasm/esbuild.wasm?url';

let initialized: Promise<typeof import('esbuild-wasm')> | undefined;
const origin = 'https://workspace.invalid';
const maxBytes = 10 * 1024 * 1024;

/** Resolve only saved workspace paths; this resolver never fetches a URL. */
export function previewPath(value: string, importer: string): string {
  if (/^[a-z][a-z0-9+.-]*:|^\/\//i.test(value) || /[\\\x00-\x1f]/.test(value))
    throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
      cause: 'preview.external_dependency',
    });
  const url = new URL(value, `${origin}/${importer.replace(/^\/+/, '')}`);
  const path = decodeURIComponent(url.pathname).slice(1);
  if (
    !path ||
    /[\\\x00-\x1f]/.test(path) ||
    path
      .split('/')
      .some((part) => !part || ['.', '..', '.owh-runtime'].includes(part))
  )
    throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
      cause: 'preview.invalid_dependency',
    });
  return path;
}

export async function bundleHtmlPreview(
  content: string,
  entry: string,
  load: (path: string) => Promise<Uint8Array>,
  signal: AbortSignal,
): Promise<string> {
  const doc = new DOMParser().parseFromString(content, 'text/html');
  const imports = new Map<string, string>();
  for (const map of doc.querySelectorAll('script[type="importmap"]')) {
    for (const [key, value] of Object.entries(
      JSON.parse(map.textContent || '{}').imports ?? {},
    )) {
      if (typeof value !== 'string')
        throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
          cause: 'preview.invalid_import_map',
        });
      imports.set(key, value);
    }
    map.remove();
  }
  const resolve = (specifier: string, importer: string) => {
    const key = [...imports.keys()]
      .sort((a, b) => b.length - a.length)
      .find(
        (key) =>
          key === specifier || (key.endsWith('/') && specifier.startsWith(key)),
      );
    if (key !== undefined) {
      const target = imports.get(key)!;
      if (key.endsWith('/') && !target.endsWith('/'))
        throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
          cause: 'preview.invalid_import_prefix',
        });
      return previewPath(target + specifier.slice(key.length), entry);
    }
    return previewPath(specifier, importer);
  };
  const cache = new Map<string, Promise<Uint8Array>>();
  let bytes = new TextEncoder().encode(content).length;
  const read = (path: string) => {
    signal.throwIfAborted();
    if (!cache.has(path)) {
      if (cache.size >= 100)
        throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
          cause: 'preview.too_many_dependencies',
        });
      cache.set(
        path,
        load(path).then((data) => {
          signal.throwIfAborted();
          bytes += data.byteLength;
          if (bytes > maxBytes)
            throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
              cause: 'preview.dependencies_too_large',
            });
          return data;
        }),
      );
    }
    return cache.get(path)!;
  };
  const compile = async (
    source: string,
    path: string,
    loader: 'js' | 'css',
  ) => {
    initialized ??= import('esbuild-wasm')
      .then(async (module) => {
        await module.initialize({ wasmURL });
        return module;
      })
      .catch((error) => {
        initialized = undefined;
        throw error;
      });
    const esbuild = await initialized;
    signal.throwIfAborted();
    const result = await esbuild.build({
      stdin: { contents: source, sourcefile: path, loader, resolveDir: '/' },
      bundle: true,
      write: false,
      format: 'iife',
      platform: 'browser',
      logLevel: 'silent',
      minify: true,
      legalComments: 'inline',
      plugins: [
        {
          name: 'saved-preview-files',
          setup(build) {
            build.onResolve({ filter: /.*/ }, (args) => {
              if (args.kind === 'url-token' && args.path.startsWith('data:'))
                return { path: args.path, external: true };
              return {
                path: resolve(args.path, args.importer || path),
                namespace: 'workspace',
              };
            });
            build.onLoad(
              { filter: /.*/, namespace: 'workspace' },
              async (args) => {
                const extension = args.path.split('.').at(-1)?.toLowerCase();
                const loaders: Record<string, Loader> = {
                  js: 'js',
                  mjs: 'js',
                  cjs: 'js',
                  jsx: 'jsx',
                  ts: 'ts',
                  tsx: 'tsx',
                  json: 'json',
                  css: 'css',
                };
                const sourceLoader = loaders[extension ?? ''] ?? 'dataurl';
                return {
                  contents: await read(args.path),
                  loader: sourceLoader,
                };
              },
            );
          },
        },
      ],
    });
    signal.throwIfAborted();
    const output = result.outputFiles[0]?.text;
    if (!output || output.length > maxBytes)
      throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
        cause: 'preview.bundle_unavailable',
      });
    return output;
  };
  for (const script of doc.querySelectorAll('script')) {
    const type = script.getAttribute('type') || '';
    if (
      !['', 'module', 'text/javascript', 'application/javascript'].includes(
        type,
      )
    )
      continue;
    const src = script.getAttribute('src');
    if (!src && type !== 'module') continue;
    const path = src ? previewPath(src, entry) : entry;
    const source = src
      ? new TextDecoder().decode(await read(path))
      : script.textContent || '';
    if (
      src &&
      type !== 'module' &&
      script.hasAttribute('defer') &&
      !script.hasAttribute('async')
    ) {
      // Inline classic scripts ignore defer. An inline module keeps the
      // browser's post-parse ordering; a real classic script retains globals
      // without eval or expanding the iframe's script-source policy.
      script.setAttribute('type', 'module');
      script.textContent = `const script=document.createElement('script');script.textContent=${JSON.stringify(source).replace(/</g, '\\u003c')};document.body.appendChild(script);`;
    } else {
      script.textContent = (
        type === 'module' ? await compile(source, path, 'js') : source
      ).replace(/<\/script/gi, '<\\/script');
    }
    for (const attr of ['src', 'integrity', 'crossorigin', 'async', 'defer'])
      script.removeAttribute(attr);
  }
  for (const link of doc.querySelectorAll('link[rel="stylesheet"]')) {
    const path = previewPath(link.getAttribute('href') || '', entry);
    const style = doc.createElement('style');
    style.textContent = await compile(
      new TextDecoder().decode(await read(path)),
      path,
      'css',
    );
    link.replaceWith(style);
  }
  for (const style of doc.querySelectorAll('style')) {
    if (/url\(|@import/i.test(style.textContent || ''))
      style.textContent = await compile(style.textContent || '', entry, 'css');
  }
  for (const image of doc.querySelectorAll('img[src]')) {
    const src = image.getAttribute('src')!;
    if (src.startsWith('data:')) continue;
    const path = previewPath(src, entry);
    const data = await read(path);
    const mime = (
      {
        png: 'image/png',
        jpg: 'image/jpeg',
        jpeg: 'image/jpeg',
        gif: 'image/gif',
        webp: 'image/webp',
        svg: 'image/svg+xml',
      } as Record<string, string>
    )[path.split('.').at(-1)!.toLowerCase()];
    if (!mime)
      throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
        cause: 'preview.unsupported_image',
      });
    let binary = '';
    for (const byte of data) binary += String.fromCharCode(byte);
    image.setAttribute('src', `data:${mime};base64,${btoa(binary)}`);
  }
  return '<!doctype html>' + doc.documentElement.outerHTML;
}
