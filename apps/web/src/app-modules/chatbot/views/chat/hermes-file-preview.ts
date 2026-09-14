import type { HermesFileRevision } from '../../api/hermes-agent-api';

export function hermesFilePreviewKind(
  file: Pick<HermesFileRevision, 'media_type' | 'relative_path'>,
): 'image' | 'html' | 'svg' | 'document' | 'code' | null {
  if (
    ['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(
      file.media_type,
    )
  )
    return 'image';
  if (file.media_type === 'image/svg+xml') return 'svg';
  if (file.media_type === 'text/html') return 'html';
  if (
    file.media_type === 'text/markdown' ||
    (file.media_type === 'text/plain' && /\.md$/i.test(file.relative_path))
  )
    return 'document';
  if (
    file.media_type.startsWith('text/') ||
    [
      'application/json',
      'application/javascript',
      'application/xml',
      'application/x-sh',
    ].includes(file.media_type)
  )
    return 'code';
  return null;
}
