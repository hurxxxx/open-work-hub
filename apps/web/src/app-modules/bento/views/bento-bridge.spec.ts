import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import { describe, expect, it, vi } from 'vitest';

const source = readFileSync(
  resolve(process.cwd(), '../../ops/bento/open-work-hub-bridge.js'),
  'utf8',
);
function bridge(mode?: 'edit' | 'read') {
  const listeners = new Map<string, (event: unknown) => void>();
  const parent = { postMessage: vi.fn() };
  const doc = document.implementation.createHTMLDocument();
  Object.defineProperty(doc, 'referrer', { value: 'https://hub.example/' });
  if (mode) {
    const script = doc.createElement('script');
    script.setAttribute('data-bento-access', mode);
    script.setAttribute('data-bento-parent', 'https://bento.example');
    Object.defineProperty(doc, 'currentScript', { value: script });
  }
  const bento = {
    doc: {
      format: 'bento/slides',
      title: 'Test',
      slides: [{}],
      collab: { secret: 'local fixture' },
    },
    format: 'bento/slides',
    loadDoc: vi.fn(),
    serialize: vi.fn(
      () =>
        '<html><body><script id="bento-doc" type="application/json">{}</script><script>officialRuntime()</script></body></html>',
    ),
  };
  const window = {
    parent,
    bento,
    location: {
      search: '?open-work-hub-embed=1',
      origin: 'https://bento.example',
      href: 'https://bento.example/',
    },
    addEventListener: (name: string, callback: (event: unknown) => void) =>
      listeners.set(name, callback),
    setInterval: vi.fn(),
    clearInterval: vi.fn(),
    setTimeout: vi.fn(),
    showSaveFilePicker: vi.fn(),
  };
  const blobs: string[] = [];
  runInNewContext(source, {
    window,
    document: doc,
    URLSearchParams,
    DOMParser,
    URL: Object.assign(class extends URL {}, {
      createObjectURL: () => 'blob:https://bento.example/viewer',
      revokeObjectURL: vi.fn(),
    }),
    Blob: class {
      constructor(parts: string[]) {
        blobs.push(parts.join(''));
      }
    },
    ArrayBuffer,
    TextDecoder,
  });
  const send = (
    data: object,
    origin = mode ? 'https://bento.example' : 'https://hub.example',
    sender: unknown = parent,
  ) =>
    listeners.get('message')?.({
      data: { channel: 'open-work-hub:bento', version: 2, ...data },
      origin,
      source: sender,
    });
  return { window, parent, doc, bento, blobs, send };
}
describe('pinned Bento bridge access boundary', () => {
  it('boots a readonly copy without ever loading content into the storage-capable editor', () => {
    const subject = bridge();
    subject.send({
      type: 'load-document',
      documentJson: JSON.stringify(subject.bento.doc),
    });
    const parsed = new DOMParser().parseFromString(
      subject.blobs[0],
      'text/html',
    );
    const copy = JSON.parse(
      parsed.getElementById('bento-doc')?.textContent || '{}',
    );
    expect(copy.readonly).toBe(true);
    expect(copy.collab).toBeUndefined();
    expect(subject.bento.loadDoc).not.toHaveBeenCalled();
    const frame = subject.doc.querySelector('iframe');
    expect(frame?.getAttribute('sandbox')).not.toContain('allow-same-origin');
    expect(frame?.getAttribute('sandbox')).toContain('allow-downloads');
    subject.send({
      type: 'load-document',
      readOnly: false,
      documentJson: JSON.stringify(subject.bento.doc),
    });
    expect(subject.blobs).toHaveLength(1);
    subject.send({ type: 'export-document' });
    expect(subject.blobs[1]).not.toContain('data-bento-access');
    expect(subject.blobs[1]).toContain('"readonly":true');
  });
  it('isolates the writable runtime and only relays from the exact opaque child', () => {
    const subject = bridge();
    const load = {
      type: 'load-document',
      readOnly: false,
      documentJson: JSON.stringify(subject.bento.doc),
    };
    subject.send(load, 'https://evil.example');
    subject.send(load, 'https://hub.example', {});
    expect(subject.blobs).toHaveLength(0);
    subject.send(load);
    expect(subject.bento.loadDoc).not.toHaveBeenCalled();
    const frame = subject.doc.querySelector('iframe');
    const child = { postMessage: vi.fn() };
    Object.defineProperty(frame, 'contentWindow', { value: child });
    expect(frame?.getAttribute('sandbox')).not.toContain('allow-same-origin');
    const save = { type: 'save-request', documentJson: '{}' };
    subject.send(save, 'null', {});
    subject.send(save, 'https://bento.example', child);
    expect(subject.parent.postMessage).not.toHaveBeenCalled();
    subject.send(save, 'null', child);
    expect(subject.parent.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining(save),
      'https://hub.example',
    );
    const exported = '<html><script>standaloneOnly()</script></html>';
    subject.send(
      { type: 'export-ready', html: exported, name: 'export.bento.html' },
      'null',
      child,
    );
    expect(subject.blobs.at(-1)).toBe(exported);
    expect(subject.doc.querySelectorAll('script')).toHaveLength(0);
    subject.send({ type: 'request-document' });
    expect(child.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'request-document' }),
      '*',
    );
  });
  it('blocks readonly child writes and accepts editor requests only from its outer bridge', async () => {
    const reader = bridge('read');
    reader.send({ type: 'request-document' });
    await expect(reader.window.showSaveFilePicker()).rejects.toThrow(
      'Read-only',
    );
    expect(reader.parent.postMessage).not.toHaveBeenCalled();
    const editor = bridge('edit');
    editor.send({ type: 'request-document' }, 'https://hub.example');
    expect(editor.parent.postMessage).not.toHaveBeenCalled();
    editor.send({ type: 'request-document' });
    expect(editor.parent.postMessage).toHaveBeenLastCalledWith(
      expect.objectContaining({ type: 'save-request' }),
      'https://bento.example',
    );
  });
});
