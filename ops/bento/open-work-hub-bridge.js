(() => {
  'use strict';

  const CHANNEL = 'open-work-hub:bento';
  const VERSION = 1;
  const POLL_INTERVAL_MS = 1000;
  const isEmbedded =
    new URLSearchParams(window.location.search).get('open-work-hub-embed') ===
    '1';

  if (!isEmbedded || window.parent === window) return;

  let parentOrigin;
  try {
    const referrer = new URL(document.referrer);
    if (referrer.protocol !== 'http:' && referrer.protocol !== 'https:') return;
    parentOrigin = referrer.origin;
  } catch {
    return;
  }

  let lastDocumentJson = null;
  let loadingDocument = false;
  let ready = false;

  function post(type, payload = {}) {
    window.parent.postMessage(
      { channel: CHANNEL, version: VERSION, type, ...payload },
      parentOrigin,
    );
  }

  function currentDocumentJson() {
    const api = window.bento;
    if (!api?.doc || api.format !== 'bento/slides') return null;
    return JSON.stringify(api.doc);
  }

  function extractDocumentJson(html) {
    const parsed = new DOMParser().parseFromString(html, 'text/html');
    const value = parsed.getElementById('bento-doc')?.textContent?.trim();
    if (!value) throw new Error('Saved Bento file did not contain a document.');
    const documentValue = JSON.parse(value);
    if (
      documentValue?.format !== 'bento/slides' ||
      !Array.isArray(documentValue.slides) ||
      documentValue.slides.length === 0
    ) {
      throw new Error('Saved document is not a valid bento/slides document.');
    }
    return JSON.stringify(documentValue);
  }

  function safeFileName(value) {
    const normalized = String(value || 'Untitled.bento.html')
      .replace(/[\\/:*?"<>|]+/g, '_')
      .trim();
    return normalized.toLowerCase().endsWith('.bento.html')
      ? normalized
      : `${normalized || 'Untitled'}.bento.html`;
  }

  function downloadHtml(html, name) {
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = safeFileName(name);
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  async function dataToText(data) {
    if (data instanceof Blob) return data.text();
    if (data instanceof ArrayBuffer) return new TextDecoder().decode(data);
    if (ArrayBuffer.isView(data)) {
      return new TextDecoder().decode(
        data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength),
      );
    }
    return String(data);
  }

  window.showSaveFilePicker = async (options = {}) => {
    const purpose = options.id === 'bento-doc' ? 'workspace-save' : 'download';
    const suggestedName = safeFileName(options.suggestedName);
    const chunks = [];
    return {
      kind: 'file',
      name: suggestedName,
      async createWritable() {
        return {
          async write(data) {
            chunks.push(await dataToText(data));
          },
          async close() {
            const html = chunks.join('');
            if (purpose === 'download') {
              downloadHtml(html, suggestedName);
              return;
            }
            const documentJson = extractDocumentJson(html);
            lastDocumentJson = documentJson;
            post('save-request', {
              documentJson,
              title: JSON.parse(documentJson).title,
            });
          },
        };
      },
    };
  };

  window.addEventListener('message', (event) => {
    if (
      event.origin !== parentOrigin ||
      event.source !== window.parent ||
      !event.data ||
      typeof event.data !== 'object' ||
      event.data.channel !== CHANNEL ||
      event.data.version !== VERSION
    ) {
      return;
    }

    try {
      if (event.data.type === 'load-document') {
        if (typeof event.data.documentJson !== 'string' || !window.bento)
          return;
        loadingDocument = true;
        const loaded = window.bento.loadDoc(event.data.documentJson);
        if (!loaded) throw new Error('Bento rejected the workspace document.');
        lastDocumentJson = currentDocumentJson();
        loadingDocument = false;
        post('loaded', {
          title: window.bento.doc?.title,
        });
        return;
      }
      if (event.data.type === 'request-document') {
        const documentJson = currentDocumentJson();
        if (!documentJson) return;
        lastDocumentJson = documentJson;
        post('save-request', {
          documentJson,
          title: window.bento.doc?.title,
        });
        return;
      }
      if (event.data.type === 'export-document') {
        const html = window.bento?.serialize?.();
        if (typeof html !== 'string') {
          throw new Error('Bento export is unavailable.');
        }
        downloadHtml(
          html,
          `${window.bento.doc?.title || 'Untitled'}.bento.html`,
        );
      }
    } catch (error) {
      loadingDocument = false;
      post('error', {
        message: error instanceof Error ? error.message : String(error),
      });
    }
  });

  const bootTimer = window.setInterval(() => {
    const documentJson = currentDocumentJson();
    if (!documentJson) return;
    if (!ready) {
      ready = true;
      lastDocumentJson = documentJson;
      post('ready', { title: window.bento.doc?.title });
      return;
    }
    if (!loadingDocument && documentJson !== lastDocumentJson) {
      lastDocumentJson = documentJson;
      post('document-changed', {
        documentJson,
        title: window.bento.doc?.title,
      });
    }
  }, POLL_INTERVAL_MS);

  window.addEventListener('pagehide', () => window.clearInterval(bootTimer));
})();
