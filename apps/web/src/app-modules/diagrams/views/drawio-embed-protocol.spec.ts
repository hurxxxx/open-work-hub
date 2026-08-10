import { describe, expect, it } from 'vitest';

import {
  buildDrawioEmbedConfig,
  buildDrawioExportMessage,
  buildDrawioLoadMessage,
  isDrawioMessageOriginAllowed,
  parseDrawioEmbedMessage,
} from './drawio-embed-protocol';

function testLocation(value: string): Location {
  return new URL(value) as unknown as Location;
}

describe('draw.io embed protocol', () => {
  it('builds a dev iframe URL from the current host and draw.io port', () => {
    const config = buildDrawioEmbedConfig({
      env: {
        DEV: true,
        VITE_AI_DO_DRAWIO_PORT: '18082',
        VITE_AI_DO_DRAWIO_URL: '/drawio/',
      },
      location: testLocation('http://100.87.48.58:4200/w/lab/diagrams'),
    });

    expect(config.origin).toBe('http://100.87.48.58:18082');
    expect(config.src).toContain('http://100.87.48.58:18082/');
    expect(config.src).toContain('embed=1');
    expect(config.src).toContain('proto=json');
  });

  it('uses an absolute configured draw.io URL for production', () => {
    const config = buildDrawioEmbedConfig({
      env: {
        DEV: false,
        VITE_AI_DO_DRAWIO_URL: 'https://drawio.dwdcc.kr/',
      },
      location: testLocation('https://dwdcc.kr/w/lab/diagrams'),
    });

    expect(config.origin).toBe('https://drawio.dwdcc.kr');
    expect(config.src).toContain('https://drawio.dwdcc.kr/');
  });

  it('builds a static dev iframe URL from the current private host when no URL is configured', () => {
    const config = buildDrawioEmbedConfig({
      env: {
        DEV: false,
        VITE_AI_DO_DRAWIO_PORT: '18082',
        VITE_AI_DO_DRAWIO_URL: '',
      },
      location: testLocation('http://100.87.48.58:4200/w/lab/diagrams'),
    });

    expect(config.origin).toBe('http://100.87.48.58:18082');
    expect(config.src).toContain('http://100.87.48.58:18082/');
  });

  it('uses the proxied draw.io path on the public dev hostname', () => {
    const config = buildDrawioEmbedConfig({
      env: {
        DEV: true,
        VITE_AI_DO_DRAWIO_PORT: '18082',
        VITE_AI_DO_DRAWIO_URL: '',
      },
      location: testLocation('https://dev.dwdcc.kr/w/lab/diagrams'),
    });

    expect(config.origin).toBe('https://dev.dwdcc.kr');
    expect(config.src).toContain('https://dev.dwdcc.kr/drawio/');
    expect(config.src).not.toContain(':18082');
  });

  it('falls back to the legacy same-origin path when no absolute production URL is configured', () => {
    const config = buildDrawioEmbedConfig({
      env: { DEV: false, VITE_AI_DO_DRAWIO_URL: '/drawio/' },
      location: testLocation('https://dwdcc.kr/w/lab/diagrams'),
    });

    expect(config.origin).toBe('https://dwdcc.kr');
    expect(config.src).toContain('https://dwdcc.kr/drawio/');
  });

  it('accepts messages only from the configured draw.io origin', () => {
    expect(
      isDrawioMessageOriginAllowed('https://app.test', 'https://app.test'),
    ).toBe(true);
    expect(
      isDrawioMessageOriginAllowed('https://evil.test', 'https://app.test'),
    ).toBe(false);
  });

  it('parses JSON string and object messages', () => {
    expect(
      parseDrawioEmbedMessage('{"event":"save","xml":"<mxfile />"}'),
    ).toEqual({
      event: 'save',
      format: undefined,
      xml: '<mxfile />',
      data: undefined,
      message: undefined,
    });
    expect(
      parseDrawioEmbedMessage({
        event: 'export',
        format: 'png',
        data: 'data:image/png;base64,abc',
      }),
    ).toEqual({
      event: 'export',
      format: 'png',
      xml: undefined,
      data: 'data:image/png;base64,abc',
      message: undefined,
    });
  });

  it('rejects non-json messages', () => {
    expect(parseDrawioEmbedMessage('ready')).toBeNull();
    expect(parseDrawioEmbedMessage(null)).toBeNull();
  });

  it('builds load and export actions', () => {
    expect(JSON.parse(buildDrawioLoadMessage('<mxfile />'))).toMatchObject({
      action: 'load',
      autosave: 1,
      xml: '<mxfile />',
    });
    expect(JSON.parse(buildDrawioExportMessage('<mxfile />'))).toMatchObject({
      action: 'export',
      format: 'png',
      xml: '<mxfile />',
    });
  });
});
