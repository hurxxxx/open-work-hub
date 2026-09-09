import { describe, expect, it, vi } from 'vitest';

import {
  clearStaleAssetReloadMarker,
  installStaleAssetReloadHandler,
  isStaleAssetLoadError,
  maybeReloadForStaleAssetLoadError,
} from './stale-asset-reload';

type Listener = (event: Event) => void;

function makeStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
  };
}

function makeRuntime(
  storage = makeStorage(),
  href = 'https://app.test/apps/pms?tab=board#panel',
) {
  const listeners = new Map<string, Listener>();
  return {
    listeners,
    runtime: {
      addEventListener: vi.fn((type: string, listener: EventListener) => {
        listeners.set(type, listener as Listener);
      }),
      removeEventListener: vi.fn((type: string) => {
        listeners.delete(type);
      }),
      location: {
        href,
        replace: vi.fn(),
      },
      history: {
        state: { key: 'router-state' },
        replaceState: vi.fn(),
      },
      sessionStorage: storage,
    },
  };
}

describe('stale asset reload recovery', () => {
  it('recognizes Vite dynamic import failures', () => {
    expect(
      isStaleAssetLoadError(
        new TypeError(
          'Failed to fetch dynamically imported module: /assets/PMSView-old.js',
        ),
      ),
    ).toBe(true);
    expect(isStaleAssetLoadError(new Error('Loading chunk 42 failed.'))).toBe(
      true,
    );
    expect(isStaleAssetLoadError(new Error('API request failed'))).toBe(false);
  });

  it('cache-busts once for stale assets within the cooldown window', () => {
    const storage = makeStorage();
    const { runtime } = makeRuntime(storage);

    expect(
      maybeReloadForStaleAssetLoadError(
        new TypeError('Failed to fetch dynamically imported module'),
        runtime,
        { nowMs: () => 1000, cooldownMs: 60_000 },
      ),
    ).toBe(true);
    expect(
      maybeReloadForStaleAssetLoadError(
        new TypeError('Failed to fetch dynamically imported module'),
        runtime,
        { nowMs: () => 2000, cooldownMs: 60_000 },
      ),
    ).toBe(false);

    expect(runtime.location.replace).toHaveBeenCalledTimes(1);
    expect(runtime.location.replace).toHaveBeenCalledWith(
      'https://app.test/apps/pms?tab=board&__reload=1000#panel',
    );
    expect(storage.setItem).toHaveBeenCalledWith(
      'open-work-hub:stale-asset-reload-at',
      '1000',
    );
  });

  it('replaces an existing cache-bust marker instead of duplicating it', () => {
    const { runtime } = makeRuntime(
      makeStorage(),
      'https://app.test/login?__reload=old&next=%2Fw%2Fhq',
    );

    expect(
      maybeReloadForStaleAssetLoadError(
        new TypeError('Failed to fetch dynamically imported module'),
        runtime,
        { nowMs: () => 2000 },
      ),
    ).toBe(true);
    expect(runtime.location.replace).toHaveBeenCalledWith(
      'https://app.test/login?__reload=2000&next=%2Fw%2Fhq',
    );
  });

  it('does not reload again when the URL already records a reload attempt', () => {
    const blockedStorage = {
      getItem: vi.fn(() => {
        throw new Error('storage blocked');
      }),
      setItem: vi.fn(() => {
        throw new Error('storage blocked');
      }),
    };
    const { runtime } = makeRuntime(
      blockedStorage,
      'https://app.test/login?__reload=1000',
    );

    expect(
      maybeReloadForStaleAssetLoadError(
        new TypeError('Failed to fetch dynamically imported module'),
        runtime,
        { nowMs: () => 2000, cooldownMs: 60_000 },
      ),
    ).toBe(false);
    expect(runtime.location.replace).not.toHaveBeenCalled();
  });

  it('removes only the cache-bust marker after bootstrap', () => {
    const { runtime } = makeRuntime(
      makeStorage(),
      'https://app.test/apps/pms?tab=board&__reload=1000#panel',
    );

    expect(clearStaleAssetReloadMarker(runtime)).toBe(true);
    expect(runtime.history.replaceState).toHaveBeenCalledWith(
      { key: 'router-state' },
      '',
      '/apps/pms?tab=board#panel',
    );
    expect(runtime.location.replace).not.toHaveBeenCalled();

    expect(
      maybeReloadForStaleAssetLoadError(
        new TypeError('Failed to fetch dynamically imported module'),
        runtime,
        { nowMs: () => 2000, cooldownMs: 60_000 },
      ),
    ).toBe(false);
  });

  it('does not rewrite history when there is no cache-bust marker', () => {
    const { runtime } = makeRuntime();

    expect(clearStaleAssetReloadMarker(runtime)).toBe(false);
    expect(runtime.history.replaceState).not.toHaveBeenCalled();
  });

  it('prevents the Vite preload error and reloads the page', () => {
    const { listeners, runtime } = makeRuntime();
    const cleanup = installStaleAssetReloadHandler(runtime, {
      nowMs: () => 3000,
      cooldownMs: 60_000,
    });
    const event = new Event('vite:preloadError', {
      cancelable: true,
    }) as Event & {
      payload: Error;
    };
    event.payload = new TypeError(
      'Failed to fetch dynamically imported module',
    );
    const preventDefault = vi.spyOn(event, 'preventDefault');

    listeners.get('vite:preloadError')?.(event);

    expect(preventDefault).toHaveBeenCalledTimes(1);
    expect(runtime.location.replace).toHaveBeenCalledTimes(1);

    cleanup();

    expect(runtime.removeEventListener).toHaveBeenCalledWith(
      'vite:preloadError',
      expect.any(Function),
    );
  });
});
