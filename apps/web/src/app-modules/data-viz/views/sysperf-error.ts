export type SysPerfNoticeTone = 'success' | 'warning' | 'danger';

export interface SysPerfNotice {
  tone: SysPerfNoticeTone;
  msg: string;
}

export function formatSysPerfErrorMessage(
  error: unknown,
  fallback: string,
): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
