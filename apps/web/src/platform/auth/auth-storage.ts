export const AUTH_TOKEN_STORAGE_KEY = 'open-work-hub.auth.token';
const AUTH_POST_LOGOUT_HOME_REDIRECT_STORAGE_KEY = 'open-work-hub.auth.post-logout-home';

type BrowserStorageName = 'localStorage' | 'sessionStorage';

interface BrowserStorageItem {
  read(): string | null;
  write(value: string): void;
  clear(): void;
}

function resolveBrowserStorage(storageName: BrowserStorageName): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window[storageName];
  } catch {
    return null;
  }
}

function withBrowserStorage<Result>(
  storageName: BrowserStorageName,
  fallback: Result,
  operation: (storage: Storage) => Result,
): Result {
  const storage = resolveBrowserStorage(storageName);
  if (!storage) {
    return fallback;
  }

  try {
    return operation(storage);
  } catch {
    return fallback;
  }
}

function createBrowserStorageItem(
  storageName: BrowserStorageName,
  key: string,
): BrowserStorageItem {
  return {
    read() {
      return withBrowserStorage(storageName, null, (storage) =>
        storage.getItem(key),
      );
    },
    write(value) {
      withBrowserStorage(storageName, undefined, (storage) => {
        storage.setItem(key, value);
      });
    },
    clear() {
      withBrowserStorage(storageName, undefined, (storage) => {
        storage.removeItem(key);
      });
    },
  };
}

const authTokenStorage = createBrowserStorageItem(
  'localStorage',
  AUTH_TOKEN_STORAGE_KEY,
);
const postLogoutHomeRedirectStorage = createBrowserStorageItem(
  'sessionStorage',
  AUTH_POST_LOGOUT_HOME_REDIRECT_STORAGE_KEY,
);

export function readStoredAuthToken(): string | null {
  return authTokenStorage.read();
}

export function persistAuthToken(token: string): void {
  authTokenStorage.write(token);
}

export function clearStoredAuthToken(): void {
  authTokenStorage.clear();
}

export function markPostLogoutHomeRedirect(): void {
  postLogoutHomeRedirectStorage.write('1');
}

export function consumePostLogoutHomeRedirect(): boolean {
  const marked = postLogoutHomeRedirectStorage.read() === '1';
  if (marked) {
    postLogoutHomeRedirectStorage.clear();
  }

  return marked;
}
