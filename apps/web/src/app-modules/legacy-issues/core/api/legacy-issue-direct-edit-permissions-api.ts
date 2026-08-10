import { apiFetchJson } from '@/src/platform/api/client';

import type { LegacyIssueModuleViewKey } from '../legacy-issue-datasets';

export interface LegacyIssueModuleDirectEditor {
  id: string;
  module_key: LegacyIssueModuleViewKey;
  user_id: string;
  display_name: string;
  email: string;
  role: 'editor' | 'manager';
  can_revoke: boolean;
  active_member: boolean;
  created_at: string;
  updated_at: string;
}

export interface LegacyIssueModuleDirectEditorListResponse {
  items: LegacyIssueModuleDirectEditor[];
}

function workspaceDirectEditorPath(workspaceSlug: string, path = ''): string {
  return `/api/v1/workspaces/${encodeURIComponent(
    workspaceSlug,
  )}/legacy-issues/module-direct-editors${path}`;
}

export function fetchLegacyIssueModuleDirectEditors({
  moduleKey,
  token,
  workspaceSlug,
}: {
  moduleKey?: LegacyIssueModuleViewKey;
  token: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleDirectEditorListResponse> {
  const search = new URLSearchParams();
  if (moduleKey) {
    search.set('module_key', moduleKey);
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : '';
  return apiFetchJson<LegacyIssueModuleDirectEditorListResponse>(
    workspaceDirectEditorPath(workspaceSlug, suffix),
    token,
  );
}

export function grantLegacyIssueModuleDirectEditor({
  moduleKey,
  token,
  userId,
  workspaceSlug,
}: {
  moduleKey: LegacyIssueModuleViewKey;
  token: string;
  userId: string;
  workspaceSlug: string;
}): Promise<LegacyIssueModuleDirectEditor> {
  return apiFetchJson<LegacyIssueModuleDirectEditor>(
    workspaceDirectEditorPath(
      workspaceSlug,
      `/${encodeURIComponent(moduleKey)}/users/${encodeURIComponent(userId)}`,
    ),
    token,
    { method: 'PUT' },
  );
}

export function revokeLegacyIssueModuleDirectEditor({
  moduleKey,
  token,
  userId,
  workspaceSlug,
}: {
  moduleKey: LegacyIssueModuleViewKey;
  token: string;
  userId: string;
  workspaceSlug: string;
}): Promise<void> {
  return apiFetchJson<void>(
    workspaceDirectEditorPath(
      workspaceSlug,
      `/${encodeURIComponent(moduleKey)}/users/${encodeURIComponent(userId)}`,
    ),
    token,
    { method: 'DELETE' },
  );
}
