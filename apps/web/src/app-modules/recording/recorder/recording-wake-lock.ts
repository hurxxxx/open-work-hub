type WakeLockSentinelLike = {
  released: boolean;
  release: () => Promise<void>;
  addEventListener?: (type: 'release', listener: () => void) => void;
};

type NavigatorWithWakeLock = Navigator & {
  wakeLock?: {
    request: (type: 'screen') => Promise<WakeLockSentinelLike>;
  };
};

function wakeLockNavigator(): NavigatorWithWakeLock | null {
  if (typeof navigator === 'undefined') {
    return null;
  }
  return navigator as NavigatorWithWakeLock;
}

export function wakeLockSupported(): boolean {
  return typeof wakeLockNavigator()?.wakeLock?.request === 'function';
}

export async function requestRecordingWakeLock(): Promise<WakeLockSentinelLike | null> {
  if (!wakeLockSupported()) {
    return null;
  }
  return await wakeLockNavigator()?.wakeLock?.request('screen') ?? null;
}
