import { describe, expect, it } from 'vitest';

import {
  createLearningContentCatalog,
  type LearningContentCatalogModules,
} from './learning-content-catalog';

function createCatalog(overrides: Partial<LearningContentCatalogModules> = {}) {
  return createLearningContentCatalog({
    lessonModules: {
      '/workspace/learning/course-b/02.md': async () => 'second lesson',
      '/workspace/learning/course-a/01.md': async () => 'first lesson',
      '/workspace/learning/README.md': async () => 'author guide',
      '/workspace/docs/not-learning.md': async () => 'ignored',
      ...overrides.lessonModules,
    },
    assetModules: {
      '/workspace/learning/course-a/assets/hero.png': '/assets/hero.123.png',
      '/workspace/learning/course-a/shared/logo.svg': '/assets/logo.456.svg',
      ...overrides.assetModules,
    },
  });
}

describe('createLearningContentCatalog', () => {
  it('loads and lists lesson files by learning-relative path', async () => {
    const catalog = createCatalog();

    expect(catalog.listAvailableLessonFiles()).toEqual([
      'course-a/01.md',
      'course-b/02.md',
    ]);
    await expect(catalog.loadLessonBody('course-a/01.md')).resolves.toBe(
      'first lesson',
    );
    await expect(catalog.loadLessonBody('course-b/02.md')).resolves.toBe(
      'second lesson',
    );
    await expect(catalog.loadLessonBody('README.md')).resolves.toBeNull();
    await expect(catalog.loadLessonBody('missing.md')).resolves.toBeNull();
  });

  it('resolves image paths relative to the lesson file', () => {
    const catalog = createCatalog();

    expect(
      catalog.resolveLessonAsset('course-a/01.md', 'assets/hero.png'),
    ).toBe('/assets/hero.123.png');
    expect(
      catalog.resolveLessonAsset('course-a/01.md', './assets/hero.png'),
    ).toBe('/assets/hero.123.png');
  });

  it('normalizes parent directory segments before matching assets', () => {
    const catalog = createCatalog();

    expect(
      catalog.resolveLessonAsset(
        'course-a/lessons/01.md',
        '../assets/hero.png',
      ),
    ).toBe('/assets/hero.123.png');
    expect(
      catalog.resolveLessonAsset(
        'course-a/lessons/01.md',
        '../shared/./logo.svg',
      ),
    ).toBe('/assets/logo.456.svg');
  });

  it('preserves query and hash suffixes on resolved assets', () => {
    const catalog = createCatalog();

    expect(
      catalog.resolveLessonAsset(
        'course-a/lessons/01.md',
        '../assets/hero.png?size=large#diagram',
      ),
    ).toBe('/assets/hero.123.png?size=large#diagram');
    expect(
      catalog.resolveLessonAsset(
        'course-a/lessons/01.md',
        '../assets/hero.png#diagram',
      ),
    ).toBe('/assets/hero.123.png#diagram');
  });

  it('passes absolute and special URL sources through unchanged', () => {
    const catalog = createCatalog();
    const sources = [
      'https://example.com/image.png',
      '//cdn.example.com/image.png',
      '/static/image.png',
      'data:image/png;base64,abc123',
      'mailto:hello@example.com',
    ];

    for (const src of sources) {
      expect(catalog.resolveLessonAsset('course-a/01.md', src)).toBe(src);
    }
  });

  it('falls back to the original source when no asset matches', () => {
    const catalog = createCatalog();

    expect(
      catalog.resolveLessonAsset(
        'course-a/01.md',
        'assets/missing.png?size=large#diagram',
      ),
    ).toBe('assets/missing.png?size=large#diagram');
    expect(
      catalog.resolveLessonAsset('course-a/01.md', undefined),
    ).toBeUndefined();
    expect(catalog.resolveLessonAsset('course-a/01.md', '')).toBe('');
  });
});
