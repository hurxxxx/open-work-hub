import { apiFetchJson } from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

export type AgentTerminalConfig = ApiSchema<'AgentTerminalConfigResponse'>;
export type AgentTerminalSession = ApiSchema<'AgentTerminalSessionResponse'>;
export type AgentTerminalSessionCreate =
  ApiSchema<'AgentTerminalSessionCreateRequest'>;
export type AgentTerminalSessionList =
  ApiSchema<'AgentTerminalSessionListResponse'>;
export type AgentTerminalGitChange =
  ApiSchema<'AgentTerminalGitChangeResponse'>;
export type AgentTerminalGitChangeScope = AgentTerminalGitChange['scope'];
export type AgentTerminalGitStatus =
  ApiSchema<'AgentTerminalGitStatusResponse'>;
export type AgentTerminalGitDiff = ApiSchema<'AgentTerminalGitDiffResponse'>;
export type AgentTerminalGitSummary =
  ApiSchema<'AgentTerminalGitSummaryResponse'>;
export type AgentTerminalGitRef = ApiSchema<'AgentTerminalGitRefResponse'>;
export type AgentTerminalGitStash = ApiSchema<'AgentTerminalGitStashResponse'>;
export type AgentTerminalGitHistory =
  ApiSchema<'AgentTerminalGitHistoryResponse'>;
export type AgentTerminalGitCommit =
  ApiSchema<'AgentTerminalGitCommitResponse'>;
export type AgentTerminalGitCommitDetail =
  ApiSchema<'AgentTerminalGitCommitDetailResponse'>;
export type AgentTerminalGitCommitFile =
  ApiSchema<'AgentTerminalGitCommitFileResponse'>;
export type AgentTerminalGitCommitDiff =
  ApiSchema<'AgentTerminalGitCommitDiffResponse'>;

const API_ROOT = '/api/v1/agent-terminal';

export function getAgentTerminalConfig(token: string) {
  return apiFetchJson<AgentTerminalConfig>(`${API_ROOT}/config`, token);
}

export function listAgentTerminalSessions(token: string) {
  return apiFetchJson<AgentTerminalSessionList>(`${API_ROOT}/sessions`, token);
}

export function createAgentTerminalSession(
  token: string,
  payload: AgentTerminalSessionCreate,
) {
  return apiFetchJson<AgentTerminalSession>(`${API_ROOT}/sessions`, token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function stopAgentTerminalSession(token: string, sessionId: string) {
  return apiFetchJson<AgentTerminalSession>(
    `${API_ROOT}/sessions/${encodeURIComponent(sessionId)}/stop`,
    token,
    { method: 'POST' },
  );
}

export function deleteAgentTerminalSession(token: string, sessionId: string) {
  return apiFetchJson<void>(
    `${API_ROOT}/sessions/${encodeURIComponent(sessionId)}`,
    token,
    { method: 'DELETE' },
  );
}

export function getAgentTerminalGitStatus(token: string, rootKey: string) {
  return apiFetchJson<AgentTerminalGitStatus>(
    `${API_ROOT}/roots/${encodeURIComponent(rootKey)}/git/status`,
    token,
  );
}

export function getAgentTerminalGitDiff(
  token: string,
  rootKey: string,
  change: Pick<AgentTerminalGitChange, 'path' | 'scope'>,
) {
  const query = new URLSearchParams({
    path: change.path,
    scope: change.scope,
  });
  return apiFetchJson<AgentTerminalGitDiff>(
    `${API_ROOT}/roots/${encodeURIComponent(rootKey)}/git/diff?${query.toString()}`,
    token,
  );
}

export function getAgentTerminalGitSummary(token: string, rootKey: string) {
  return apiFetchJson<AgentTerminalGitSummary>(
    `${API_ROOT}/roots/${encodeURIComponent(rootKey)}/git/summary`,
    token,
  );
}

export function getAgentTerminalGitHistory(
  token: string,
  rootKey: string,
  options: { limit?: number; offset?: number } = {},
) {
  const query = new URLSearchParams({
    limit: String(options.limit ?? 50),
    offset: String(options.offset ?? 0),
  });
  return apiFetchJson<AgentTerminalGitHistory>(
    `${API_ROOT}/roots/${encodeURIComponent(rootKey)}/git/history?${query.toString()}`,
    token,
  );
}

export function getAgentTerminalGitCommit(
  token: string,
  rootKey: string,
  commit: string,
) {
  return apiFetchJson<AgentTerminalGitCommitDetail>(
    `${API_ROOT}/roots/${encodeURIComponent(rootKey)}/git/commits/${encodeURIComponent(commit)}`,
    token,
  );
}

export function getAgentTerminalGitCommitDiff(
  token: string,
  rootKey: string,
  commit: string,
  path: string,
) {
  const query = new URLSearchParams({ path });
  return apiFetchJson<AgentTerminalGitCommitDiff>(
    `${API_ROOT}/roots/${encodeURIComponent(rootKey)}/git/commits/${encodeURIComponent(commit)}/diff?${query.toString()}`,
    token,
  );
}

export function agentTerminalWebSocketUrl(sessionId: string): string {
  const url = new URL(
    `${API_ROOT}/sessions/${encodeURIComponent(sessionId)}/ws`,
    window.location.origin,
  );
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return window.btoa(binary);
}

export function base64ToBytes(value: string): Uint8Array {
  const binary = window.atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}
