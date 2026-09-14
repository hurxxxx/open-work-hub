import { i18n } from '@/src/platform/i18n';
import type { BuildOptions, Loader } from 'esbuild-wasm';
import wasmURL from 'esbuild-wasm/esbuild.wasm?url';

let initialized: Promise<typeof import('esbuild-wasm')> | undefined;
const origin = 'https://workspace.invalid';
const maxBytes = 10 * 1024 * 1024;
const modulePrefix = `${origin}/__modules__/`;

function dataUrl(type: string, bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `data:${type};base64,${btoa(binary)}`;
}

function invalidPathCharacters(value: string): boolean {
  for (const character of value) {
    if (character === '\\' || character.charCodeAt(0) < 32) return true;
  }
  return false;
}

/** Resolve only saved workspace paths; this resolver never fetches a URL. */
export function previewPath(value: string, importer: string): string {
  if (/^[a-z][a-z0-9+.-]*:|^\/\//i.test(value) || invalidPathCharacters(value))
    throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
      cause: 'preview.external_dependency',
    });
  const url = new URL(value, `${origin}/${importer.replace(/^\/+/, '')}`);
  const path = decodeURIComponent(url.pathname).slice(1);
  if (
    !path ||
    invalidPathCharacters(path) ||
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
  const modules = new Map<
    string,
    {
      script: HTMLScriptElement;
      path: string;
      source: string;
      external: boolean;
    }
  >();
  const build = async (options: BuildOptions, path: string) => {
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
      bundle: true,
      write: false,
      format: 'esm',
      platform: 'browser',
      logLevel: 'silent',
      minify: true,
      legalComments: 'inline',
      ...options,
      plugins: [
        {
          name: 'saved-preview-files',
          setup(build) {
            build.onResolve({ filter: /.*/ }, (args) => {
              if (args.kind === 'entry-point') {
                const module = modules.get(args.path);
                if (module)
                  return module.external
                    ? { path: module.path, namespace: 'workspace' }
                    : { path: args.path, namespace: 'inline' };
              }
              if (args.kind === 'url-token' && args.path.startsWith('data:'))
                return { path: args.path, external: true };
              return {
                path: resolve(
                  args.path,
                  modules.get(args.importer)?.path || args.importer || path,
                ),
                namespace: 'workspace',
              };
            });
            build.onLoad({ filter: /.*/, namespace: 'inline' }, (args) => ({
              contents: modules.get(args.path)?.source ?? '',
              loader: 'js',
            }));
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
    if (
      !result.outputFiles?.length ||
      result.outputFiles.reduce(
        (size, file) => size + file.contents.byteLength,
        0,
      ) > maxBytes
    )
      throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
        cause: 'preview.bundle_unavailable',
      });
    return result.outputFiles;
  };
  const compile = async (source: string, path: string, loader: 'css') => {
    const output = await build(
      {
        stdin: { contents: source, sourcefile: path, loader, resolveDir: '/' },
      },
      path,
    );
    return output[0].text;
  };
  for (const script of doc.querySelectorAll('script')) {
    const type = script.getAttribute('type') || '';
    if (
      !['', 'module', 'text/javascript', 'application/javascript'].includes(
        type,
      )
    )
      continue;
    if (type !== 'module' && script.hasAttribute('nomodule')) {
      script.remove();
      continue;
    }
    const src = script.getAttribute('src');
    if (!src && type !== 'module') continue;
    const path = src ? previewPath(src, entry) : entry;
    const source = src
      ? new TextDecoder().decode(await read(path))
      : script.textContent || '';
    if (type === 'module') {
      const key = `entry${modules.size}`;
      modules.set(key, { script, path, source, external: !!src });
      script.removeAttribute('src');
      script.textContent = `import ${JSON.stringify(`${modulePrefix}${key}.js`)};`;
    } else {
      // Native external-script loading preserves parser blocking, defer,
      // async, global declarations and ordering. Bytes remain embedded.
      script.setAttribute(
        'src',
        dataUrl('text/javascript', new TextEncoder().encode(source)),
      );
      script.textContent = '';
    }
    for (const attr of ['integrity', 'crossorigin'])
      script.removeAttribute(attr);
  }
  if (modules.size) {
    const outputs = await build(
      {
        entryPoints: [...modules.keys()].map((key) => ({ in: key, out: key })),
        splitting: true,
        outdir: '/preview',
        publicPath: modulePrefix,
      },
      entry,
    );
    const moduleMap: Record<string, string> = {};
    for (const output of outputs) {
      if (output.path.endsWith('.css')) {
        const style = doc.createElement('style');
        style.textContent = output.text;
        doc.head.appendChild(style);
      } else {
        moduleMap[modulePrefix + output.path.split('/').at(-1)] = dataUrl(
          'text/javascript',
          output.contents,
        );
      }
    }
    const map = doc.createElement('script');
    map.type = 'importmap';
    map.textContent = JSON.stringify({ imports: moduleMap });
    doc.head.prepend(map);
  }
  for (const link of doc.querySelectorAll('link[rel="stylesheet"]')) {
    const path = previewPath(link.getAttribute('href') || '', entry);
    const style = doc.createElement('style');
    const media = link.getAttribute('media');
    if (media !== null) style.setAttribute('media', media);
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
    image.setAttribute('src', dataUrl(mime, data));
  }
  const html = '<!doctype html>' + doc.documentElement.outerHTML;
  if (new TextEncoder().encode(html).byteLength > maxBytes)
    throw new Error(i18n.t('apps:ai.htmlArtifact.previewFailed'), {
      cause: 'preview.bundle_unavailable',
    });
  return html;
}
