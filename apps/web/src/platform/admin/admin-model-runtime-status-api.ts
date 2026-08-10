import { jsonHeaders } from '@/src/platform/api/client';

export type ModelRuntimeStatus =
  | 'online'
  | 'degraded'
  | 'offline'
  | 'not_configured';

export interface ModelRuntimeModel {
  name: string;
  task: string | null;
  loaded: boolean;
}

export interface ModelRuntimeTarget {
  id: string;
  display_name: string;
  kind: 'inference_gateway' | 'llm';
  role: 'serving' | 'redundancy' | 'diagnostic';
  provider_id: string | null;
  status: ModelRuntimeStatus;
  models: ModelRuntimeModel[];
  error_code:
    | 'connection_failed'
    | 'http_error'
    | 'invalid_response'
    | 'model_missing'
    | 'configuration_invalid'
    | 'timeout'
    | null;
}

export interface AdminModelRuntimeStatusSnapshot {
  checked_at: string;
  status: 'online' | 'degraded' | 'offline';
  targets: ModelRuntimeTarget[];
}

export class AdminModelRuntimeStatusApiError extends Error {}

export async function getAdminModelRuntimeStatus(
  token: string,
): Promise<AdminModelRuntimeStatusSnapshot> {
  const response = await fetch('/api/v1/admin/model-runtime-status', {
    cache: 'no-store',
    headers: jsonHeaders(token),
  });
  if (!response.ok) {
    throw new AdminModelRuntimeStatusApiError();
  }
  return (await response.json()) as AdminModelRuntimeStatusSnapshot;
}
