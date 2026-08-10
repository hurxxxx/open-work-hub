import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

const API_V1_PREFIX = '/api/v1';
const CHATBOT_API_PREFIX = `${API_V1_PREFIX}/chatbot`;

export function resolveWorkspaceChatbotApiPath(
  rawPath: string,
  workspaceSlug?: string | null,
): string {
  if (workspaceSlug && rawPath.startsWith(CHATBOT_API_PREFIX)) {
    return `/api/v1/workspaces/${encodeURIComponent(workspaceSlug)}${rawPath.slice(API_V1_PREFIX.length)}`;
  }
  return rewriteWorkspaceApiPath(rawPath, workspaceSlug);
}
