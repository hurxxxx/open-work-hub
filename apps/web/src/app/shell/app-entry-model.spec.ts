import { describe, expect, it } from 'vitest';

import type { AppsBootstrapApp } from '@/src/platform/workspaces/workspaces-api';
import {
  projectAppEntryQueryParams,
  resolveAppEntryDecision,
} from './app-entry-model';

const workspace = {
  id: 'workspace-1',
  name: 'Workspace 1',
  slug: 'workspace-1',
};

function app(overrides: Partial<AppsBootstrapApp> = {}): AppsBootstrapApp {
  return {
    app_id: 'docs',
    availability_scope: 'workspace',
    coming_soon: false,
    eligible_workspace_count: 2,
    entry_route_id: 'docs.root',
    execution_context_kind: 'workspace',
    icon_key: 'files',
    preferred_workspace: null,
    resource_scope: 'workspace',
    route_base: '/apps/docs',
    single_eligible_workspace: null,
    title: 'Docs',
    ...overrides,
  };
}

describe('app entry model', () => {
  it('removes obsolete workspace query context from canonical entry routes', () => {
    expect(
      projectAppEntryQueryParams(
        new URLSearchParams(
          'workspace=old&workspace_id=old-id&workspaceSlug=old-slug&view=mine',
        ),
      ),
    ).toEqual({ view: 'mine' });
  });

  it('enters platform apps without workspace context', () => {
    expect(
      resolveAppEntryDecision(
        app({
          app_id: 'mail',
          availability_scope: 'platform',
          eligible_workspace_count: 0,
          entry_route_id: 'mail.root',
          execution_context_kind: 'personal',
          resource_scope: 'personal',
          route_base: '/apps/mail',
        }),
      ),
    ).toEqual({ href: '/apps/mail', kind: 'global' });
  });

  it('fails closed when a workspace app has no eligible workspace', () => {
    expect(
      resolveAppEntryDecision(app({ eligible_workspace_count: 0 })),
    ).toEqual({ kind: 'unavailable' });
  });

  it('uses an eligible app-specific preference without rewriting it', () => {
    expect(
      resolveAppEntryDecision(app({ preferred_workspace: workspace })),
    ).toEqual({
      kind: 'workspace',
      persistPreference: false,
      workspace,
    });
  });

  it('persists and enters a single eligible workspace', () => {
    expect(
      resolveAppEntryDecision(
        app({
          eligible_workspace_count: 1,
          single_eligible_workspace: workspace,
        }),
      ),
    ).toEqual({ kind: 'workspace', persistPreference: true, workspace });
  });

  it('requires an app-local choice for multiple eligible workspaces', () => {
    expect(resolveAppEntryDecision(app())).toEqual({
      kind: 'choose-workspace',
    });
  });
});
