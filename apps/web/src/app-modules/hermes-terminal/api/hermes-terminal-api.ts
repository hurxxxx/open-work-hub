import {
  apiFetchBinary,
  apiFetchJson,
  type ApiBinaryResponse,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type HermesTerminalConfig = ApiSchema<'HermesTerminalConfigResponse'>;
export type HermesTerminalSession = ApiSchema<'HermesTerminalSessionResponse'>;
export type HermesTerminalSessionCreate =
  ApiSchema<'HermesTerminalSessionCreateRequest'>;
export type HermesTerminalSessionList =
  ApiSchema<'HermesTerminalSessionListResponse'>;
export type HermesTerminalFileEntry =
  ApiSchema<'HermesTerminalFileEntryResponse'>;
export type HermesTerminalFileList =
  ApiSchema<'HermesTerminalFileListResponse'>;
export type HermesTerminalApproval =
  ApiSchema<'HermesTerminalApprovalResponse'>;
export type HermesTerminalApprovalList =
  ApiSchema<'HermesTerminalApprovalListResponse'>;
export type HermesTerminalApprovalDecision =
  ApiSchema<'HermesTerminalApprovalDecisionRequest'>;

const API_ROOT = '/api/v1/hermes-terminal';

function workspacePath(path: string, workspaceSlug: string): string {
  return rewriteWorkspaceApiPath(`${API_ROOT}${path}`, workspaceSlug);
}

export function getHermesTerminalConfig(token: string, workspaceSlug: string) {
  return apiFetchJson<HermesTerminalConfig>(
    workspacePath('/config', workspaceSlug),
    token,
  );
}

export function listHermesTerminalSessions(
  token: string,
  workspaceSlug: string,
) {
  return apiFetchJson<HermesTerminalSessionList>(
    workspacePath('/sessions', workspaceSlug),
    token,
  );
}

export function createHermesTerminalSession(
  token: string,
  workspaceSlug: string,
  payload: HermesTerminalSessionCreate,
) {
  return apiFetchJson<HermesTerminalSession>(
    workspacePath('/sessions', workspaceSlug),
    token,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function stopHermesTerminalSession(
  token: string,
  workspaceSlug: string,
  sessionId: string,
) {
  return apiFetchJson<HermesTerminalSession>(
    workspacePath(
      `/sessions/${encodeURIComponent(sessionId)}/stop`,
      workspaceSlug,
    ),
    token,
    { method: 'POST' },
  );
}

export function listHermesTerminalFiles(
  token: string,
  workspaceSlug: string,
  sessionId: string,
  path = '',
) {
  const query = new URLSearchParams({ path });
  return apiFetchJson<HermesTerminalFileList>(
    workspacePath(
      `/sessions/${encodeURIComponent(sessionId)}/files?${query.toString()}`,
      workspaceSlug,
    ),
    token,
  );
}

export function downloadHermesTerminalFile(
  token: string,
  workspaceSlug: string,
  sessionId: string,
  path: string,
): Promise<ApiBinaryResponse> {
  const query = new URLSearchParams({ path });
  return apiFetchBinary(
    workspacePath(
      `/sessions/${encodeURIComponent(sessionId)}/files/download?${query.toString()}`,
      workspaceSlug,
    ),
    token,
  );
}

export function listHermesTerminalApprovals(
  token: string,
  workspaceSlug: string,
  sessionId: string,
) {
  return apiFetchJson<HermesTerminalApprovalList>(
    workspacePath(
      `/sessions/${encodeURIComponent(sessionId)}/approvals`,
      workspaceSlug,
    ),
    token,
  );
}

export function decideHermesTerminalApproval(
  token: string,
  workspaceSlug: string,
  sessionId: string,
  approvalId: string,
  payload: HermesTerminalApprovalDecision,
) {
  return apiFetchJson<HermesTerminalApproval>(
    workspacePath(
      `/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}`,
      workspaceSlug,
    ),
    token,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function hermesTerminalWebSocketUrl(
  workspaceSlug: string,
  sessionId: string,
): string {
  const path = workspacePath(
    `/sessions/${encodeURIComponent(sessionId)}/ws`,
    workspaceSlug,
  );
  const url = new URL(path, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}
