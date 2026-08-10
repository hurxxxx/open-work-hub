const worker = globalThis;

worker.addEventListener('install', (event) => {
  event.waitUntil(worker.skipWaiting());
});

worker.addEventListener('activate', (event) => {
  event.waitUntil(worker.clients.claim());
});

async function notifyRecordingClients() {
  const clients = await worker.clients.matchAll({
    type: 'window',
    includeUncontrolled: true,
  });
  await Promise.all(
    clients.map((client) => client.postMessage({ type: 'ai-do-recording-sync' })),
  );
}

worker.addEventListener('sync', (event) => {
  if (event.tag === 'ai-do-recording-upload') {
    event.waitUntil(notifyRecordingClients());
  }
});
