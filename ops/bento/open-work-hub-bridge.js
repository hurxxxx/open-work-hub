function installBentoBridge() {
  'use strict';
  const CHANNEL = 'open-work-hub:bento';
  const VERSION = 2;
  const POLL_INTERVAL_MS = 1000;
  const bootScript = document.currentScript;
  const childMode = bootScript?.getAttribute('data-bento-access');
  const isChild = childMode === 'read' || childMode === 'edit';
  const isEmbedded =
    isChild ||
    new URLSearchParams(window.location.search).get('open-work-hub-embed') ===
      '1';
  if (!isEmbedded || window.parent === window) return;
  let parentOrigin;
  try {
    const parentUrl = new URL(
      isChild
        ? bootScript.getAttribute('data-bento-parent')
        : document.referrer,
    );
    if (!['http:', 'https:'].includes(parentUrl.protocol)) return;
    parentOrigin = parentUrl.origin;
  } catch {
    return;
  }
  let lastDocumentJson = null;
  let ready = false;
  const readOnly = childMode !== 'edit';
  let childFrame = null;
  let childUrl = null;
  let exportedHtml = null;
  let contentTitle = null;
  let accessMode = null;

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
    const doc = JSON.parse(value);
    if (
      doc?.format !== 'bento/slides' ||
      !Array.isArray(doc.slides) ||
      doc.slides.length === 0
    )
      throw new Error('Invalid Bento document.');
    return JSON.stringify(doc);
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
    if (isChild) {
      post('export-ready', { html, name });
      return;
    }
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

  function bootDocument(documentJson, requestedReadOnly) {
    if (accessMode !== null && accessMode !== requestedReadOnly) return;
    accessMode = requestedReadOnly;
    // v1.0.17 has no public setting to disable IndexedDB recovery/assets, and
    // loadDoc cannot switch to the official presentation-only player. Boot the
    // serialized official runtime in an opaque sandbox; the outer editor never
    // receives content. This also prevents cross-account browser persistence.
    const parsed = new DOMParser().parseFromString(
      window.bento.serialize(),
      'text/html',
    );
    parsed.querySelectorAll('script[src]').forEach((script) => {
      if (
        new URL(script.getAttribute('src'), window.location.href).pathname ===
        '/open-work-hub-bridge.js'
      )
        script.remove();
    });
    const slot = parsed.getElementById('bento-doc');
    if (!slot) throw new Error('Bento export is unavailable.');
    const copy = JSON.parse(documentJson);
    contentTitle = copy.title;
    copy.readonly = requestedReadOnly;
    delete copy.collab;
    slot.textContent = JSON.stringify(copy).replace(/</g, '\\u003c');
    exportedHtml = '<!DOCTYPE html>\n' + parsed.documentElement.outerHTML;
    const script = parsed.createElement('script');
    script.setAttribute(
      'data-bento-access',
      requestedReadOnly ? 'read' : 'edit',
    );
    script.setAttribute('data-bento-parent', window.location.origin);
    script.textContent = '(' + installBentoBridge.toString() + ')();';
    parsed.body.append(script);
    const html = '<!DOCTYPE html>\n' + parsed.documentElement.outerHTML;
    if (childUrl) URL.revokeObjectURL(childUrl);
    childUrl = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    childFrame = document.createElement('iframe');
    childFrame.title = copy.title || 'Bento';
    childFrame.src = childUrl;
    // Do not add allow-same-origin: native storage isolation is the boundary.
    childFrame.setAttribute(
      'sandbox',
      'allow-downloads allow-forms allow-modals allow-pointer-lock allow-presentation allow-scripts',
    );
    childFrame.setAttribute('allowfullscreen', '');
    childFrame.style.cssText =
      'position:fixed;inset:0;width:100%;height:100%;border:0;background:white';
    document.body.replaceChildren(childFrame);
  }

  if (isChild) {
    window.showSaveFilePicker = async (options = {}) => {
      if (readOnly) throw new Error('Read-only document.');
      const purpose = options.id === 'bento-doc' ? 'hub-save' : 'download';
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
  }

  window.addEventListener('message', (event) => {
    const message = event.data;
    if (
      !message ||
      typeof message !== 'object' ||
      message.channel !== CHANNEL ||
      message.version !== VERSION
    )
      return;
    if (
      !isChild &&
      childFrame &&
      event.source === childFrame.contentWindow &&
      event.origin === 'null'
    ) {
      if (message.type === 'ready') {
        post('loaded', { title: contentTitle });
        return;
      }
      if (message.type === 'error') {
        post('error', { message: message.message });
        return;
      }
      if (
        accessMode === false &&
        message.type === 'export-ready' &&
        typeof message.html === 'string'
      ) {
        downloadHtml(message.html, message.name);
        return;
      }
      if (
        accessMode === false &&
        ['save-request', 'document-changed'].includes(message.type) &&
        typeof message.documentJson === 'string'
      ) {
        post(message.type, {
          documentJson: message.documentJson,
          title: message.title,
        });
      }
      return;
    }
    if (event.origin !== parentOrigin || event.source !== window.parent) return;
    try {
      if (!isChild) {
        if (
          message.type === 'load-document' &&
          typeof message.documentJson === 'string' &&
          window.bento?.serialize
        ) {
          bootDocument(message.documentJson, message.readOnly !== false);
        } else if (
          message.type === 'export-document' &&
          accessMode === true &&
          exportedHtml
        ) {
          downloadHtml(
            exportedHtml,
            `${contentTitle || 'Untitled'}.bento.html`,
          );
        } else if (
          accessMode === false &&
          ['request-document', 'export-document'].includes(message.type)
        ) {
          // Opaque frames require '*'; only this exact owned Window receives
          // token-free commands. Replies require that Window AND origin null.
          childFrame?.contentWindow?.postMessage(message, '*');
        }
        return;
      }
      if (message.type === 'request-document' && !readOnly) {
        const documentJson = currentDocumentJson();
        if (!documentJson) return;
        lastDocumentJson = documentJson;
        post('save-request', { documentJson, title: window.bento.doc?.title });
      } else if (message.type === 'export-document' && !readOnly) {
        const html = window.bento?.serialize?.();
        if (typeof html !== 'string')
          throw new Error('Bento export is unavailable.');
        downloadHtml(
          html,
          `${window.bento.doc?.title || 'Untitled'}.bento.html`,
        );
      }
    } catch (error) {
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
    if (isChild && !readOnly && documentJson !== lastDocumentJson) {
      lastDocumentJson = documentJson;
      post('document-changed', {
        documentJson,
        title: window.bento.doc?.title,
      });
    }
  }, POLL_INTERVAL_MS);
  window.addEventListener('pagehide', () => {
    window.clearInterval(bootTimer);
    if (childUrl) URL.revokeObjectURL(childUrl);
  });
}
installBentoBridge();
