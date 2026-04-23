import type { WorkspaceBootstrapApp } from '@/src/domains/workspaces/workspaces-api';

export const SEARCHABLE_RAG_APP_IDS = ['docs', 'meeting', 'pms', 'planner'] as const;

export function getEnabledWorkspaceAppIds(
  apps: Pick<WorkspaceBootstrapApp, 'app_id' | 'enabled'>[] | null | undefined,
): Set<string> {
  return new Set(
    (apps ?? [])
      .filter((app) => app.enabled)
      .map((app) => app.app_id),
  );
}

export function isWorkspaceAppEnabled(
  apps: Pick<WorkspaceBootstrapApp, 'app_id' | 'enabled'>[] | null | undefined,
  appId: string,
): boolean {
  return getEnabledWorkspaceAppIds(apps).has(appId);
}

export function canUseWorkspaceSearchTool(
  apps: Pick<WorkspaceBootstrapApp, 'app_id' | 'enabled'>[] | null | undefined,
): boolean {
  const enabledAppIds = getEnabledWorkspaceAppIds(apps);
  return (
    enabledAppIds.has('ai')
    && SEARCHABLE_RAG_APP_IDS.some((appId) => enabledAppIds.has(appId))
  );
}
