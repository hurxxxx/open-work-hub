import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';
import { i18n } from '@/src/platform/i18n';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export class AiApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function resolveErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (
      detail &&
      typeof detail === 'object' &&
      'message' in detail &&
      typeof detail.message === 'string'
    ) {
      return detail.message;
    }
  }
  return fallback;
}

async function aiRequest<T>(
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJsonWithMappedError<T>(
      rewriteWorkspaceApiPath(path),
      token,
      init,
      (error) =>
        new AiApiError(
          error.status,
          resolveErrorMessage(
            error.payload,
            i18n.t('apps:ai.errors.requestFailed', { status: error.status }),
          ),
        ),
    );
  } catch (error) {
    if (error instanceof AiApiError) throw error;
    throw new AiApiError(0, i18n.t('apps:ai.errors.connect'));
  }
}

export interface ToolInvokeEnvelope<T> {
  tool: string;
  owner_domain: string;
  approval_required: boolean;
  result: T;
}

export function invokeAiTool<T>(
  toolName: string,
  args: Record<string, unknown>,
  token: string,
): Promise<T> {
  return aiRequest<ToolInvokeEnvelope<T>>(
    `/api/v1/chatbot/tools/${encodeURIComponent(toolName)}/invoke`,
    token,
    {
      method: 'POST',
      body: JSON.stringify({ arguments: args }),
    },
  ).then((envelope) => envelope.result);
}
