import { describe, expect, it, vi } from 'vitest';

import {
  createMediaUrlResolutionSession,
  type MediaUrlResolutionScheduler,
  type ResolveMediaUrlsAdapter,
} from './media-url-resolution-session';

type ScheduledTask = Parameters<MediaUrlResolutionScheduler>[0];

async function runScheduledTask(tasks: ScheduledTask[]) {
  const task = tasks.shift();
  if (!task) {
    throw new Error('Expected a scheduled task');
  }
  await task();
}

describe('media URL resolution session', () => {
  it('passes through non-media URLs and media URLs without a token', async () => {
    const resolveMediaUrls = vi.fn<ResolveMediaUrlsAdapter>(async () => ({}));
    const schedule = vi.fn<MediaUrlResolutionScheduler>();
    const session = createMediaUrlResolutionSession({
      resolveMediaUrls,
      schedule,
    });

    await expect(
      session.resolveFileUrl({
        token: 'token-1',
        url: 'https://cdn.example/already-resolved.png',
      }),
    ).resolves.toBe('https://cdn.example/already-resolved.png');
    await expect(
      session.resolveFileUrl({ token: undefined, url: 'media:image-1' }),
    ).resolves.toBe('media:image-1');

    expect(schedule).not.toHaveBeenCalled();
    expect(resolveMediaUrls).not.toHaveBeenCalled();
  });

  it('batches media URLs requested in the same scheduled task', async () => {
    const tasks: ScheduledTask[] = [];
    const resolveMediaUrls = vi.fn<ResolveMediaUrlsAdapter>(
      async (_token, urls) => ({
        ...Object.fromEntries(urls.map((url) => [url, `resolved:${url}`])),
        'media:image-1': 'https://cdn.example/image-1.png',
        'media:image-2': 'https://cdn.example/image-2.png',
      }),
    );
    const session = createMediaUrlResolutionSession({
      resolveMediaUrls,
      now: () => 1000,
      schedule: (task) => {
        tasks.push(task);
      },
    });

    const first = session.resolveFileUrl({
      token: 'token-1',
      url: 'media:image-1',
    });
    const second = session.resolveFileUrl({
      token: 'token-1',
      url: 'media:image-2',
    });
    const duplicate = session.resolveFileUrl({
      token: 'token-1',
      url: 'media:image-1',
    });

    expect(tasks).toHaveLength(1);
    expect(resolveMediaUrls).not.toHaveBeenCalled();

    await runScheduledTask(tasks);

    await expect(Promise.all([first, second, duplicate])).resolves.toEqual([
      'https://cdn.example/image-1.png',
      'https://cdn.example/image-2.png',
      'https://cdn.example/image-1.png',
    ]);
    expect(resolveMediaUrls).toHaveBeenCalledTimes(1);
    expect(resolveMediaUrls).toHaveBeenCalledWith('token-1', [
      'media:image-1',
      'media:image-2',
    ]);
  });

  it('returns cached resolved URLs until the TTL expires', async () => {
    let currentNow = 1000;
    const resolveMediaUrls = vi.fn<ResolveMediaUrlsAdapter>(async () => ({
      'media:image-1': 'https://cdn.example/image-1.png',
    }));
    const session = createMediaUrlResolutionSession({
      resolveMediaUrls,
      now: () => currentNow,
      schedule: (task) => {
        void task();
      },
      cacheTtlMs: 100,
    });

    await expect(
      session.resolveFileUrl({ token: 'token-1', url: 'media:image-1' }),
    ).resolves.toBe('https://cdn.example/image-1.png');

    currentNow = 1099;
    await expect(
      session.resolveFileUrl({ token: 'token-1', url: 'media:image-1' }),
    ).resolves.toBe('https://cdn.example/image-1.png');
    expect(resolveMediaUrls).toHaveBeenCalledTimes(1);

    currentNow = 1101;
    await expect(
      session.resolveFileUrl({ token: 'token-1', url: 'media:image-1' }),
    ).resolves.toBe('https://cdn.example/image-1.png');
    expect(resolveMediaUrls).toHaveBeenCalledTimes(2);
  });

  it('falls back to the original media URL when resolution fails', async () => {
    const resolveMediaUrls = vi.fn<ResolveMediaUrlsAdapter>(async () => {
      throw new Error('resolve failed');
    });
    const session = createMediaUrlResolutionSession({
      resolveMediaUrls,
      schedule: (task) => {
        void task();
      },
    });

    await expect(
      session.resolveFileUrl({ token: 'token-1', url: 'media:image-1' }),
    ).resolves.toBe('media:image-1');
    expect(resolveMediaUrls).toHaveBeenCalledWith('token-1', ['media:image-1']);
  });

  it('revokes a late object URL and resolves safely after disposal', async () => {
    const tasks: ScheduledTask[] = [];
    let finishResolution: ((value: Record<string, string>) => void) | null =
      null;
    const resolveMediaUrls = vi.fn<ResolveMediaUrlsAdapter>(
      () =>
        new Promise((resolve) => {
          finishResolution = resolve;
        }),
    );
    const revokeObjectUrl = vi
      .spyOn(URL, 'revokeObjectURL')
      .mockImplementation(() => undefined);
    const session = createMediaUrlResolutionSession({
      resolveMediaUrls,
      schedule: (task) => tasks.push(task),
    });
    const pending = session.resolveFileUrl({
      token: 'token-1',
      url: 'media:image-1',
    });
    const task = tasks.shift();
    if (!task) throw new Error('Expected a scheduled task');
    const flushing = task();
    await Promise.resolve();

    session.dispose();
    finishResolution?.({ 'media:image-1': 'blob:late-image' });
    await flushing;

    await expect(pending).resolves.toBe('media:image-1');
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:late-image');
    await expect(
      session.resolveFileUrl({ token: 'token-1', url: 'media:image-2' }),
    ).resolves.toBe('media:image-2');
  });
});
