// Bundle every learning/*.md file at build time as a raw string. The glob
// reaches five levels up to the repo-root `learning/` directory. Vite
// resolves the pattern statically, so new files require a restart.
const modules = import.meta.glob('../../../../../learning/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const byFilename: Record<string, string> = {};
for (const [absPath, body] of Object.entries(modules)) {
  const name = absPath.split('/').pop();
  if (name) {
    byFilename[name] = body;
  }
}

export function getLessonBody(file: string): string | null {
  return byFilename[file] ?? null;
}

export function listAvailableLessonFiles(): string[] {
  return Object.keys(byFilename).sort();
}
