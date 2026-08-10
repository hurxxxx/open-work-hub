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
    clients.map((client) => client.postMessage({ type: 'open-work-hub-recording-sync' })),
  );
}

worker.addEventListener('sync', (event) => {
  if (event.tag === 'open-work-hub-recording-upload') {
    event.waitUntil(notifyRecordingClients());
  }
});
