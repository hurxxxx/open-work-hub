import { describe, expect, it } from 'vitest';

import { artifactDownloadSpec } from './artifact-download';

describe('artifactDownloadSpec', () => {
  it('downloads HTML artifacts as html files', () => {
    expect(
      artifactDownloadSpec({
        id: 'artifact-1',
        language: null,
        title: '간단한 카드',
        type: 'html',
      }),
    ).toEqual({
      filename: '간단한-카드.html',
      mimeType: 'text/html;charset=utf-8',
    });
  });

  it('uses the code language for known code extensions', () => {
    expect(
      artifactDownloadSpec({
        id: 'artifact-2',
        language: 'python',
        title: 'FastAPI route',
        type: 'code',
      }).filename,
    ).toBe('FastAPI-route.py');
  });

  it('sanitizes unsafe filename characters', () => {
    expect(
      artifactDownloadSpec({
        id: 'artifact-3',
        language: null,
        title: 'A/B: C?',
        type: 'document',
      }).filename,
    ).toBe('A-B-C.md');
  });
});
