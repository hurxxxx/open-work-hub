import type { ArtifactBuffer } from '../../../api/agent-events';

export interface ArtifactDownloadSpec {
  filename: string;
  mimeType: string;
}

const LANGUAGE_EXTENSIONS: Record<string, string> = {
  bash: 'sh',
  css: 'css',
  html: 'html',
  javascript: 'js',
  js: 'js',
  json: 'json',
  markdown: 'md',
  md: 'md',
  python: 'py',
  py: 'py',
  shell: 'sh',
  sh: 'sh',
  sql: 'sql',
  ts: 'ts',
  tsx: 'tsx',
  typescript: 'ts',
  yaml: 'yml',
  yml: 'yml',
};

export function artifactDownloadSpec(
  artifact: Pick<ArtifactBuffer, 'id' | 'language' | 'title' | 'type'>,
): ArtifactDownloadSpec {
  const extension = artifactExtension(artifact);
  const basename = sanitizeFileBasename(
    artifact.title?.trim() || `${artifact.type}-${artifact.id.slice(0, 8)}`,
  );
  return {
    filename: `${basename}.${extension}`,
    mimeType: artifactMimeType(artifact),
  };
}

function artifactExtension(
  artifact: Pick<ArtifactBuffer, 'language' | 'type'>,
): string {
  switch (artifact.type) {
    case 'html':
      return 'html';
    case 'svg':
      return 'svg';
    case 'document':
      return 'md';
    case 'code': {
      const language = artifact.language?.trim().toLowerCase();
      return language ? (LANGUAGE_EXTENSIONS[language] ?? 'txt') : 'txt';
    }
    default:
      return 'txt';
  }
}

function artifactMimeType(artifact: Pick<ArtifactBuffer, 'type'>): string {
  switch (artifact.type) {
    case 'html':
      return 'text/html;charset=utf-8';
    case 'svg':
      return 'image/svg+xml;charset=utf-8';
    case 'document':
      return 'text/markdown;charset=utf-8';
    default:
      return 'text/plain;charset=utf-8';
  }
}

function sanitizeFileBasename(value: string): string {
  const safe = value
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return safe || 'artifact';
}
