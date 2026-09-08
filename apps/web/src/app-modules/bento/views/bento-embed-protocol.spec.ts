import { describe, expect, it } from 'vitest';

import {
  buildBentoEmbedConfig,
  buildBentoExportMessage,
  buildBentoLoadMessage,
  isBentoMessageOriginAllowed,
  parseBentoBridgeMessage,
} from './bento-embed-protocol';

function testLocation(value: string): Location {
  return new URL(value) as unknown as Location;
}

describe('bento embed protocol', () => {
  it('builds a separate-origin local iframe URL', () => {
    const config = buildBentoEmbedConfig({
      env: { DEV: true, VITE_OPEN_WORK_HUB_BENTO_PORT: '18084' },
      location: testLocation('http://127.0.0.1:4200/apps/bento'),
    });
    expect(config).toEqual({
      src: 'http://127.0.0.1:18084/?open-work-hub-embed=1',
      origin: 'http://127.0.0.1:18084',
    });
  });

  it('rejects same-origin and non-http production URLs', () => {
    expect(
      buildBentoEmbedConfig({
        env: { VITE_OPEN_WORK_HUB_BENTO_URL: '/bento/' },
        location: testLocation('https://hub.example/apps/bento'),
      }),
    ).toBeNull();
    expect(
      buildBentoEmbedConfig({
        env: { VITE_OPEN_WORK_HUB_BENTO_URL: 'data:text/html,not-bento' },
        location: testLocation('https://hub.example/apps/bento'),
      }),
    ).toBeNull();
    expect(
      buildBentoEmbedConfig({
        env: { VITE_OPEN_WORK_HUB_BENTO_URL: 'http://bento.example/' },
        location: testLocation('https://hub.example/apps/bento'),
      }),
    ).toBeNull();
  });

  it('accepts only the configured origin and protocol envelope', () => {
    expect(
      isBentoMessageOriginAllowed(
        'https://bento.example',
        'https://bento.example',
      ),
    ).toBe(true);
    expect(
      isBentoMessageOriginAllowed(
        'https://evil.example',
        'https://bento.example',
      ),
    ).toBe(false);
    expect(
      parseBentoBridgeMessage({
        channel: 'open-work-hub:bento',
        version: 1,
        type: 'document-changed',
        documentJson: '{"format":"bento/slides"}',
      }),
    ).toMatchObject({ type: 'document-changed' });
    expect(
      parseBentoBridgeMessage({ channel: 'wrong', version: 1, type: 'ready' }),
    ).toBeNull();
  });

  it('builds load and export host messages', () => {
    expect(buildBentoLoadMessage('{}')).toMatchObject({
      type: 'load-document',
      documentJson: '{}',
    });
    expect(buildBentoExportMessage()).toMatchObject({
      type: 'export-document',
    });
  });
});
