// Bundle every learning/**/*.md file at build time as a raw string. The
// glob walks the repo-root `learning/` directory recursively, so new
// courses added under `learning/<course-slug>/` are picked up with no
// loader changes. The top-level `README.md` is excluded since it is a
// content-author guide, not a lesson body.
const modules = import.meta.glob('../../../../../../learning/**/*.md', {
  query: '?raw',
  import: 'default',
}) as Record<string, () => Promise<string>>;

// Keys are keyed by path relative to `learning/` (e.g.
// `vibe-coding-foundations/01-오리엔테이션.md`) so the manifest can
// address any lesson regardless of nesting depth.
const LEARNING_DIR_MARKER = '/learning/';
const byRelativePath: Record<string, () => Promise<string>> = {};
for (const [absPath, loadBody] of Object.entries(modules)) {
  const markerIndex = absPath.lastIndexOf(LEARNING_DIR_MARKER);
  if (markerIndex < 0) continue;
  const relative = absPath.slice(markerIndex + LEARNING_DIR_MARKER.length);
  // Skip repo-root README at `learning/README.md` — it's author-facing
  // documentation, not a lesson. Anything inside a course folder is
  // kept (two or more path segments, e.g. `vcf/00-index.md`).
  if (!relative.includes('/')) continue;
  byRelativePath[relative] = loadBody;
}

export async function loadLessonBody(file: string): Promise<string | null> {
  const loadBody = byRelativePath[file];
  if (!loadBody) return null;
  return loadBody();
}

export function listAvailableLessonFiles(): string[] {
  return Object.keys(byRelativePath).sort();
}
