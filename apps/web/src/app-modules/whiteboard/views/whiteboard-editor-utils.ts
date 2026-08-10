import { colorForCollaborativeUser } from '@open-alm/ui';

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';
export type CollabStatus =
  | 'connecting'
  | 'connected'
  | 'offline'
  | 'error'
  | null;

export function waitFor(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function colorForUser(userId: string): string {
  return colorForCollaborativeUser(userId);
}

export function decodeBase64ToUint8Array(value: string): Uint8Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function encodeUint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return window.btoa(binary);
}

export function toWebSocketUrl(wsPath: string): string {
  const resolved = new URL(wsPath, window.location.origin);
  resolved.protocol = resolved.protocol === 'https:' ? 'wss:' : 'ws:';
  return resolved.toString();
}

export function collabLabel(
  status: CollabStatus,
  t: (key: string) => string,
): string {
  if (status === 'connecting') return t('whiteboard.collabConnecting');
  if (status === 'connected') return t('whiteboard.collabLive');
  if (status === 'offline' || status === 'error')
    return t('whiteboard.collabOffline');
  return '';
}

export function safeFilename(title: string, extension: string): string {
  const base =
    title
      .trim()
      .replace(/[^a-zA-Z0-9가-힣._-]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'whiteboard';
  return `${base}.${extension}`;
}

export function saveLabel(
  status: SaveStatus,
  t: (key: string) => string,
): string {
  return {
    idle: '',
    dirty: t('common:actions.saving'),
    saving: t('common:actions.saving'),
    saved: t('whiteboard.saved'),
    error: t('whiteboard.saveFailed'),
  }[status];
}
