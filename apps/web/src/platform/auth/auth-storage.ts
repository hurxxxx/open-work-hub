export const AUTH_TOKEN_STORAGE_KEY = 'ai-do.auth.token';
export const AUTH_POST_LOGOUT_HOME_REDIRECT_STORAGE_KEY = 'ai-do.auth.post-logout-home';

export function readStoredAuthToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function persistAuthToken(token: string): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
}

export function clearStoredAuthToken(): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
}

export function markPostLogoutHomeRedirect(): void {
  if (typeof window === 'undefined') {
    return;
  }

  window.sessionStorage.setItem(AUTH_POST_LOGOUT_HOME_REDIRECT_STORAGE_KEY, '1');
}

export function consumePostLogoutHomeRedirect(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  const marked = window.sessionStorage.getItem(AUTH_POST_LOGOUT_HOME_REDIRECT_STORAGE_KEY) === '1';
  if (marked) {
    window.sessionStorage.removeItem(AUTH_POST_LOGOUT_HOME_REDIRECT_STORAGE_KEY);
  }

  return marked;
}
