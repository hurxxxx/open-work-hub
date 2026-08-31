import type {
  AppsBootstrapApp,
  EligibleWorkspace,
} from '@/src/platform/workspaces/workspaces-api';
import type { AppId } from '@open-work-hub/contracts/app-contracts';
import { buildAppEntryHref } from '@open-work-hub/contracts/app-routes';

export type AppEntryDecision =
  | { kind: 'unavailable' }
  | { href: string; kind: 'global' }
  | {
      kind: 'workspace';
      persistPreference: boolean;
      workspace: EligibleWorkspace;
    }
  | { kind: 'choose-workspace' };

const OBSOLETE_WORKSPACE_QUERY_KEYS = new Set([
  'workspace',
  'workspace_id',
  'workspaceSlug',
]);

export function projectAppEntryQueryParams(
  searchParams: URLSearchParams,
): Record<string, string> {
  return Object.fromEntries(
    [...searchParams].filter(
      ([key]) => !OBSOLETE_WORKSPACE_QUERY_KEYS.has(key),
    ),
  );
}

export function resolveAppEntryDecision(
  app: AppsBootstrapApp | null,
): AppEntryDecision {
  if (!app) {
    return { kind: 'unavailable' };
  }
  if (app.availability_scope === 'platform') {
    return {
      href: buildAppEntryHref(app.app_id as AppId),
      kind: 'global',
    };
  }
  if (app.eligible_workspace_count < 1) {
    return { kind: 'unavailable' };
  }
  if (app.preferred_workspace) {
    return {
      kind: 'workspace',
      persistPreference: false,
      workspace: app.preferred_workspace,
    };
  }
  if (app.single_eligible_workspace) {
    return {
      kind: 'workspace',
      persistPreference: true,
      workspace: app.single_eligible_workspace,
    };
  }
  return { kind: 'choose-workspace' };
}
