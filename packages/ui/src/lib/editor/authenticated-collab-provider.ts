import { WebsocketProvider } from 'y-websocket';
import type { Doc } from 'yjs';

export function createAuthenticatedCollabProvider({
  url,
  roomKey,
  doc,
  token,
}: {
  url: string;
  roomKey: string;
  doc: Doc;
  token: string;
}): WebsocketProvider {
  const target = new URL(url);
  if (
    !['ws:', 'wss:'].includes(target.protocol) ||
    target.search ||
    target.hash ||
    target.username ||
    target.password ||
    !token
  ) {
    throw new Error('COLLAB_CONNECTION_PARAMETERS_INVALID');
  }
  const provider = new WebsocketProvider(url, roomKey, doc, {
    connect: false,
    maxBackoffTime: 4000,
    // Every disclosure must pass the server's current session and source ACL.
    disableBc: true,
  });
  // y-websocket 3.0.0 emits connected synchronously before its initial Yjs sync.
  // Register before the caller connects; the same handler authenticates retries.
  provider.on('status', ({ status }: { status: string }) => {
    if (status === 'connected') {
      provider.ws?.send(JSON.stringify({ type: 'auth', token }));
    }
  });
  return provider;
}
