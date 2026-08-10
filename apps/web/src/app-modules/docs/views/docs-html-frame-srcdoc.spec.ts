import { describe, expect, it } from 'vitest';

import {
  buildDocsHtmlFrameSrcDoc,
  insertDocsHtmlFrameInserts,
  normalizeDocsHtmlZoom,
} from './docs-html-frame-srcdoc';

describe('docs-html-frame-srcdoc', () => {
  it('normalizes invalid and high-precision zoom values', () => {
    expect(normalizeDocsHtmlZoom(Number.NaN)).toBe(1);
    expect(normalizeDocsHtmlZoom(0)).toBe(1);
    expect(normalizeDocsHtmlZoom(1.234)).toBe(1.23);
  });

  it('places inserts inside an existing head element', () => {
    expect(
      insertDocsHtmlFrameInserts(
        '<html><head></head><body>Report</body></html>',
        '<style>html{zoom:1.5}</style>',
      ),
    ).toBe(
      '<html><head><style>html{zoom:1.5}</style></head><body>Report</body></html>',
    );
  });

  it('adds a head element when only html exists', () => {
    expect(
      insertDocsHtmlFrameInserts(
        '<html><body>Report</body></html>',
        '<style>html{zoom:1.5}</style>',
      ),
    ).toBe(
      '<html><head><style>html{zoom:1.5}</style></head><body>Report</body></html>',
    );
  });

  it('prepends inserts to HTML fragments', () => {
    expect(
      insertDocsHtmlFrameInserts('<section>Report</section>', '<script></script>'),
    ).toBe('<script></script><section>Report</section>');
  });

  it('builds zoom and wheel bridge inserts together', () => {
    const srcDoc = buildDocsHtmlFrameSrcDoc('<html><head></head><body /></html>', 1.5, {
      enableWheelBridge: true,
    });

    expect(srcDoc).toContain('data-open-alm-html-zoom');
    expect(srcDoc).toContain('zoom:1.50');
    expect(srcDoc).toContain('data-open-alm-wheel-bridge');
  });

  it('returns content unchanged when no inserts are needed', () => {
    expect(buildDocsHtmlFrameSrcDoc('<p>Report</p>', -1)).toBe('<p>Report</p>');
  });
});
