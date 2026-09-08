import {
  apiFetchBinary,
  apiFetchJson,
  type ApiBinaryResponse,
} from '@/src/platform/api/client';
import type { ApiSchema } from '@/src/platform/api/types';

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

function apiPath(path: string): string {
  return `${API_ROOT}${path}`;
}

export function getHermesTerminalConfig(token: string) {
  return apiFetchJson<HermesTerminalConfig>(apiPath('/config'), token);
}

export function listHermesTerminalSessions(token: string) {
  return apiFetchJson<HermesTerminalSessionList>(apiPath('/sessions'), token);
}

export function createHermesTerminalSession(
  token: string,
  payload: HermesTerminalSessionCreate,
) {
  return apiFetchJson<HermesTerminalSession>(apiPath('/sessions'), token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function stopHermesTerminalSession(token: string, sessionId: string) {
  return apiFetchJson<HermesTerminalSession>(
    apiPath(`/sessions/${encodeURIComponent(sessionId)}/stop`),
    token,
    { method: 'POST' },
  );
}

export function listHermesTerminalFiles(
  token: string,
  sessionId: string,
  path = '',
) {
  const query = new URLSearchParams({ path });
  return apiFetchJson<HermesTerminalFileList>(
    apiPath(
      `/sessions/${encodeURIComponent(sessionId)}/files?${query.toString()}`,
    ),
    token,
  );
}

export function downloadHermesTerminalFile(
  token: string,
  sessionId: string,
  path: string,
): Promise<ApiBinaryResponse> {
  const query = new URLSearchParams({ path });
  return apiFetchBinary(
    apiPath(
      `/sessions/${encodeURIComponent(sessionId)}/files/download?${query.toString()}`,
    ),
    token,
  );
}

export function listHermesTerminalApprovals(token: string, sessionId: string) {
  return apiFetchJson<HermesTerminalApprovalList>(
    apiPath(`/sessions/${encodeURIComponent(sessionId)}/approvals`),
    token,
  );
}

export function decideHermesTerminalApproval(
  token: string,
  sessionId: string,
  approvalId: string,
  payload: HermesTerminalApprovalDecision,
) {
  return apiFetchJson<HermesTerminalApproval>(
    apiPath(
      `/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}`,
    ),
    token,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function hermesTerminalWebSocketUrl(sessionId: string): string {
  const path = apiPath(`/sessions/${encodeURIComponent(sessionId)}/ws`);
  const url = new URL(path, window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}
