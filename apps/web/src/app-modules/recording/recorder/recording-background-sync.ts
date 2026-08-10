const RECORDING_SYNC_TAG = 'ai-do-recording-upload';
const RECORDING_SYNC_WORKER = '/recording-sync-sw.js';

type SyncRegistration = ServiceWorkerRegistration & {
  sync?: {
    register: (tag: string) => Promise<void>;
  };
};

function serviceWorkerSupported(): boolean {
  return typeof navigator !== 'undefined' && 'serviceWorker' in navigator;
}

export async function registerRecordingBackgroundSync(): Promise<boolean> {
  if (!serviceWorkerSupported()) {
    return false;
  }
  try {
    const registration = await navigator.serviceWorker.register(RECORDING_SYNC_WORKER);
    const sync = (registration as SyncRegistration).sync;
    if (!sync) {
      return false;
    }
    await sync.register(RECORDING_SYNC_TAG);
    return true;
  } catch {
    return false;
  }
}

export function bindRecordingBackgroundSync(onSync: () => void): () => void {
  if (!serviceWorkerSupported()) {
    return () => undefined;
  }
  const handleMessage = (event: MessageEvent) => {
    if (event.data?.type === 'ai-do-recording-sync') {
      onSync();
    }
  };
  navigator.serviceWorker.addEventListener('message', handleMessage);
  void navigator.serviceWorker.register(RECORDING_SYNC_WORKER).catch(() => undefined);
  return () => navigator.serviceWorker.removeEventListener('message', handleMessage);
}
