import { createLearningContentCatalog } from './learning-content-catalog';

// Bundle every learning/**/*.md file at build time as a raw string. The
// glob walks the repo-root `learning/` directory recursively, so new
// courses added under `learning/<course-slug>/` are picked up with no
// loader changes. The top-level `README.md` is excluded since it is a
// content-author guide, not a lesson body.
const modules = import.meta.glob(
  [
    '../../../../../../learning/**/*.md',
    '!../../../../../../learning/README.md',
    '!../../../../../../learning/**/assets/**/*.md',
  ],
  {
    query: '?raw',
    import: 'default',
  },
) as Record<string, () => Promise<string>>;

const assetModules = import.meta.glob(
  '../../../../../../learning/**/assets/**/*.{gif,jpeg,jpg,png,svg,webp}',
  {
    query: '?url',
    import: 'default',
    eager: true,
  },
) as Record<string, string>;

const catalog = createLearningContentCatalog({
  lessonModules: modules,
  assetModules,
});

export async function loadLessonBody(file: string): Promise<string | null> {
  return catalog.loadLessonBody(file);
}

export function listAvailableLessonFiles(): string[] {
  return catalog.listAvailableLessonFiles();
}

export function resolveLessonAsset(
  lessonFile: string,
  src: string | undefined,
): string | undefined {
  return catalog.resolveLessonAsset(lessonFile, src);
}
