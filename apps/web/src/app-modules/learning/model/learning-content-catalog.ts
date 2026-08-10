export type LessonBodyLoader = () => Promise<string>;

export interface LearningContentCatalogModules {
  lessonModules: Record<string, LessonBodyLoader>;
  assetModules: Record<string, string>;
}

export interface LearningContentCatalog {
  loadLessonBody(file: string): Promise<string | null>;
  listAvailableLessonFiles(): string[];
  resolveLessonAsset(
    lessonFile: string,
    src: string | undefined,
  ): string | undefined;
}

const LEARNING_DIR_MARKER = '/learning/';
const COURSE_LESSON_PATH_PATTERN = /\//;
const ABSOLUTE_OR_SPECIAL_SRC = /^(?:[a-z][a-z\d+.-]*:|\/\/|\/)/i;

function toLearningRelativePath(modulePath: string): string | null {
  const markerIndex = modulePath.lastIndexOf(LEARNING_DIR_MARKER);
  if (markerIndex < 0) return null;
  return modulePath.slice(markerIndex + LEARNING_DIR_MARKER.length);
}

function normalizeRelativePath(path: string): string {
  const segments: string[] = [];
  for (const segment of path.split('/')) {
    if (!segment || segment === '.') continue;
    if (segment === '..') {
      segments.pop();
      continue;
    }
    segments.push(segment);
  }
  return segments.join('/');
}

function createLessonBodyLoaders(
  lessonModules: Record<string, LessonBodyLoader>,
): Record<string, LessonBodyLoader> {
  const byRelativePath: Record<string, LessonBodyLoader> = {};
  for (const [modulePath, loadBody] of Object.entries(lessonModules)) {
    const relativePath = toLearningRelativePath(modulePath);
    if (!relativePath || !COURSE_LESSON_PATH_PATTERN.test(relativePath))
      continue;
    byRelativePath[relativePath] = loadBody;
  }
  return byRelativePath;
}

function createAssetUrls(
  assetModules: Record<string, string>,
): Record<string, string> {
  const assetByRelativePath: Record<string, string> = {};
  for (const [modulePath, assetUrl] of Object.entries(assetModules)) {
    const relativePath = toLearningRelativePath(modulePath);
    if (!relativePath) continue;
    assetByRelativePath[relativePath] = assetUrl;
  }
  return assetByRelativePath;
}

export function createLearningContentCatalog({
  lessonModules,
  assetModules,
}: LearningContentCatalogModules): LearningContentCatalog {
  const lessonBodyLoaders = createLessonBodyLoaders(lessonModules);
  const assetUrls = createAssetUrls(assetModules);

  return {
    async loadLessonBody(file: string): Promise<string | null> {
      const loadBody = lessonBodyLoaders[file];
      if (!loadBody) return null;
      return loadBody();
    },

    listAvailableLessonFiles(): string[] {
      return Object.keys(lessonBodyLoaders).sort();
    },

    resolveLessonAsset(
      lessonFile: string,
      src: string | undefined,
    ): string | undefined {
      if (!src || ABSOLUTE_OR_SPECIAL_SRC.test(src)) return src;

      const suffixStart = src.search(/[?#]/);
      const pathPart = suffixStart >= 0 ? src.slice(0, suffixStart) : src;
      const suffix = suffixStart >= 0 ? src.slice(suffixStart) : '';
      const lessonDir = lessonFile.slice(0, lessonFile.lastIndexOf('/') + 1);
      const resolvedPath = normalizeRelativePath(`${lessonDir}${pathPart}`);
      const assetUrl = assetUrls[resolvedPath];

      return assetUrl ? `${assetUrl}${suffix}` : src;
    },
  };
}
