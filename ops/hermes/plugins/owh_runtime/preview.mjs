// Chromium's public DevTools pipe; runs only in the disposable offline sandbox.
import { spawn } from 'node:child_process';
import { constants } from 'node:fs';
import { open, realpath, readdir } from 'node:fs/promises';
import { extname } from 'node:path';

const entry = process.argv[2];
const root = '/workspace/';
const origin = 'https://workspace.invalid';
const maxBytes = 10 * 1024 * 1024;
let browser, nextId = 0, buffer = '', usedBytes = 0;
const pending = new Map(), handlers = new Map(), cache = new Map();
const errors = [];
const report = (message) => { if (errors.length < 20) errors.push(String(message).slice(0, 300)); };
const csp = "default-src 'none'; script-src 'unsafe-inline' data: https://workspace.invalid; style-src 'unsafe-inline' https://workspace.invalid; img-src data: blob: https://workspace.invalid; font-src data: https://workspace.invalid; connect-src 'none'; base-uri 'none'; form-action 'none'; sandbox allow-scripts";
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = ++nextId;
  pending.set(id, { resolve, reject });
  browser.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + '\0');
});
const read = async (path) => {
  if (cache.has(path)) return cache.get(path);
  if (cache.size >= 100 || path.split('/').some(p => !p || ['.', '..', '.owh-runtime'].includes(p))
    || /[\\\x00-\x1f]/.test(path)) throw new Error('Invalid or excessive preview dependency');
  const fd = await open(root + path, constants.O_RDONLY | constants.O_NONBLOCK);
  try {
    if (!(await realpath(`/proc/self/fd/${fd.fd}`)).startsWith(root)) throw new Error('Preview path escaped workspace');
    const stat = await fd.stat();
    if (!stat.isFile() || stat.size > 2 * 1024 * 1024) throw new Error('Preview file is not a bounded regular file');
    const data = Buffer.alloc(stat.size + 1);
    const { bytesRead } = await fd.read(data, 0, data.length, 0);
    if (bytesRead !== stat.size) throw new Error('Preview file changed during read');
    usedBytes += bytesRead;
    if (usedBytes > maxBytes) throw new Error('Preview dependencies exceed 10 MiB');
    const result = data.subarray(0, bytesRead);
    cache.set(path, result);
    return result;
  } finally { await fd.close(); }
};
const timer = setTimeout(() => {
  browser?.kill('SIGKILL');
  process.stdout.write(JSON.stringify({ error: 'preview.timeout', errors }));
  process.exit(1);
}, 25_000);

try {
  await read(entry);
  const browserRoot = '/opt/hermes/.playwright';
  const releases = (await readdir(browserRoot)).filter(name => name.startsWith('chromium_headless_shell-'));
  if (releases.length !== 1) throw new Error('preview.browser_unavailable');
  const folders = (await readdir(`${browserRoot}/${releases[0]}`)).filter(name => name.startsWith('chrome-headless-shell-'));
  if (folders.length !== 1) throw new Error('preview.browser_unavailable');
  const executable = `${browserRoot}/${releases[0]}/${folders[0]}/chrome-headless-shell`;
  browser = spawn(executable, ['--headless', '--remote-debugging-pipe',
    '--disable-background-networking', '--disable-component-update', '--no-first-run',
    '--no-proxy-server', '--host-resolver-rules=MAP * ~NOTFOUND',
    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
    '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
    '--user-data-dir=/tmp/owh-preview-profile', '--disable-dev-shm-usage', 'about:blank'],
  { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] });
  browser.stderr.on('data', () => {}); // Never return raw browser/host diagnostics.
  browser.on('exit', () => {
    for (const waiter of pending.values()) waiter.reject(new Error('preview.browser_start_failed'));
    pending.clear();
  });
  browser.stdio[4].on('data', data => {
    buffer += data.toString();
    let end;
    while ((end = buffer.indexOf('\0')) !== -1) {
      const message = JSON.parse(buffer.slice(0, end)); buffer = buffer.slice(end + 1);
      if (message.id) {
        const waiter = pending.get(message.id); pending.delete(message.id);
        if (message.error) waiter?.reject(new Error('preview.protocol_error'));
        else waiter?.resolve(message.result);
      } else handlers.get(message.method)?.(message);
    }
  });
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const call = (method, params) => send(method, params, sessionId);
  handlers.set('Fetch.requestPaused', async ({ params }) => {
    try {
      const url = new URL(params.request.url);
      if (url.origin !== origin) throw new Error('External preview dependency blocked');
      const path = decodeURIComponent(url.pathname).slice(1);
      const data = await read(path);
      const type = ({ '.html': 'text/html', '.htm': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
        '.css': 'text/css', '.json': 'application/json', '.png': 'image/png',
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml',
        '.webp': 'image/webp', '.gif': 'image/gif', '.woff2': 'font/woff2' })[extname(path).toLowerCase()];
      if (!type) throw new Error('Unsupported preview dependency type');
      await call('Fetch.fulfillRequest', { requestId: params.requestId, responseCode: 200,
        responseHeaders: [{ name: 'Content-Type', value: type },
          { name: 'Access-Control-Allow-Origin', value: '*' },
          { name: 'Content-Security-Policy', value: csp }], body: data.toString('base64') });
    } catch (error) {
      report(error.message);
      await call('Fetch.failRequest', { requestId: params.requestId, errorReason: 'BlockedByClient' }).catch(() => {});
    }
  });
  handlers.set('Runtime.exceptionThrown', ({ params }) => report(
    params.exceptionDetails.exception?.description || params.exceptionDetails.text));
  handlers.set('Runtime.consoleAPICalled', ({ params }) => {
    if (['error', 'assert'].includes(params.type)) report(
      params.args.map(arg => arg.description || arg.value || arg.type).join(' '));
  });
  handlers.set('Log.entryAdded', ({ params }) => {
    if (params.entry.level === 'error') report(params.entry.text);
  });
  await call('Page.enable'); await call('Runtime.enable'); await call('Log.enable');
  await call('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  await call('Emulation.setDeviceMetricsOverride', { width: 1024, height: 768,
    deviceScaleFactor: 1, mobile: false });
  const loaded = new Promise(resolve => handlers.set('Page.loadEventFired', resolve));
  await call('Page.navigate', { url: `${origin}/${entry.split('/').map(encodeURIComponent).join('/')}` });
  await loaded;
  await new Promise(resolve => setTimeout(resolve, 1500));
  const { result } = await call('Runtime.evaluate', { expression:
    `JSON.stringify({title:document.title,text:document.body?.innerText.slice(0,1500),canvases:[...document.querySelectorAll('canvas')].map(c=>({width:c.width,height:c.height}))})`,
    returnByValue: true });
  const screenshot = await call('Page.captureScreenshot', { format: 'jpeg', quality: 60 });
  if (screenshot.data.length > 512 * 1024) throw new Error('preview.screenshot_too_large');
  // Check the real renderer namespace/filters before accepting visual evidence.
  let secured = false;
  for (const pid of (await readdir('/proc')).filter(name => /^\d+$/.test(name))) {
    try {
      const { readFile, readlink } = await import('node:fs/promises');
      const cmd = await readFile(`/proc/${pid}/cmdline`, 'utf8');
      if (!cmd.includes('--type=renderer')) continue;
      const status = await readFile(`/proc/${pid}/status`, 'utf8');
      secured ||= /Seccomp:\s+2/.test(status) && /NoNewPrivs:\s+1/.test(status)
        && await readlink(`/proc/${pid}/ns/pid`) !== await readlink('/proc/self/ns/pid')
        && await readlink(`/proc/${pid}/ns/net`) !== await readlink('/proc/self/ns/net');
    } catch {}
  }
  if (!secured) throw new Error('preview.browser_sandbox_unverified');
  console.log(JSON.stringify({ status: errors.length ? 'render_errors' : 'rendered',
    errors, page: JSON.parse(result.value), files: [...cache.keys()], screenshot: screenshot.data }));
} catch (error) {
  console.log(JSON.stringify({ error: String(error.message).slice(0, 300), errors }));
  process.exitCode = 1;
} finally {
  clearTimeout(timer);
  browser?.kill('SIGKILL');
}
