export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  is_admin: boolean;
}

export interface AuthSession {
  token: string;
  user: AuthUser;
}

export interface BootstrapStatus {
  requires_setup: boolean;
}

export interface SetupPayload {
  fullName: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export const AUTH_TOKEN_STORAGE_KEY = 'aidoo.auth.token';

class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    cache: 'no-store',
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, payload?.detail ?? `Request failed with ${response.status}.`);
  }

  return payload as T;
}

export function getBootstrapStatus(): Promise<BootstrapStatus> {
  return request<BootstrapStatus>('/api/v1/auth/bootstrap-status');
}

export function setupFirstUser(payload: SetupPayload): Promise<AuthSession> {
  return request<AuthSession>('/api/v1/auth/setup', {
    method: 'POST',
    body: JSON.stringify({
      full_name: payload.fullName,
      email: payload.email,
      password: payload.password,
    }),
  });
}

export function login(payload: LoginPayload): Promise<AuthSession> {
  return request<AuthSession>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function me(token: string): Promise<AuthUser> {
  return request<AuthUser>('/api/v1/auth/me', {}, token);
}

export function logout(token: string): Promise<void> {
  return request<void>('/api/v1/auth/logout', { method: 'POST' }, token);
}
