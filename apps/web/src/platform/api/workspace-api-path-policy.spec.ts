import { beforeEach, describe, expect, it } from 'vitest';

import { APP_WORKSPACE_API_ROUTE_POLICY } from '@/src/app/shell/workspace-api-routes';
import {
  configureWorkspaceApiRoutePolicy,
  getWorkspaceApiPrefixes,
  resetWorkspaceApiRoutePolicy,
  rewriteWorkspaceApiPathForWorkspace,
} from './workspace-api-path-policy';
import { createWorkspaceApiRoutePolicy } from './workspace-api-route-policy';

describe('workspace API path policy', () => {
  beforeEach(() => {
    resetWorkspaceApiRoutePolicy();
    configureWorkspaceApiRoutePolicy(APP_WORKSPACE_API_ROUTE_POLICY);
  });

  it('rewrites configured app API prefixes into workspace-scoped paths', () => {
    expect(rewriteWorkspaceApiPathForWorkspace('/api/v1/rag/query', 'hq')).toBe(
      '/api/v1/workspaces/hq/rag/query',
    );
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/retrieval/query', 'hq'),
    ).toBe('/api/v1/workspaces/hq/retrieval/query');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/writing-assistant/jobs',
        'hq',
      ),
    ).toBe('/api/v1/workspaces/hq/writing-assistant/jobs');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/meeting/meetings', 'hq'),
    ).toBe('/api/v1/workspaces/hq/meeting/meetings');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/calendar/events', 'hq'),
    ).toBe('/api/v1/calendar/events');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/planner/events', 'hq'),
    ).toBe('/api/v1/planner/events');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/announcements', 'hq'),
    ).toBe('/api/v1/workspaces/hq/announcements');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/recording/recordings', 'hq'),
    ).toBe('/api/v1/workspaces/hq/recording/recordings');
    expect(rewriteWorkspaceApiPathForWorkspace('/api/v1/docs/hub', 'hq')).toBe(
      '/api/v1/workspaces/hq/docs/hub',
    );
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/docs?view=mine', 'hq'),
    ).toBe('/api/v1/workspaces/hq/docs?view=mine');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/whiteboard/hub', 'hq'),
    ).toBe('/api/v1/workspaces/hq/whiteboard/hub');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/diagrams/hub', 'hq'),
    ).toBe('/api/v1/workspaces/hq/diagrams/hub');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/search/documents/imports',
        'hq',
      ),
    ).toBe('/api/v1/workspaces/hq/search/documents/imports');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/connectors/ocr/jobs', 'hq'),
    ).toBe('/api/v1/workspaces/hq/connectors/ocr/jobs');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/wiki/pages', 'hq'),
    ).toBe('/api/v1/workspaces/hq/wiki/pages');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/web-search/ask/stream',
        'hq',
      ),
    ).toBe('/api/v1/workspaces/hq/web-search/ask/stream');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/writing-assistant/records',
        'hq',
      ),
    ).toBe('/api/v1/workspaces/hq/writing-assistant/records');
  });

  it('collects workspace API prefixes from app manifests and platform route policy', () => {
    expect(getWorkspaceApiPrefixes()).toEqual(
      expect.arrayContaining([
        '/api/v1/chatbot',
        '/api/v1/announcements',
        '/api/v1/connectors',
        '/api/v1/docs',
        '/api/v1/diagrams',
        '/api/v1/pms',
        '/api/v1/writing-assistant',
        '/api/v1/retrieval',
        '/api/v1/search',
        '/api/v1/web-search',
        '/api/v1/wiki',
      ]),
    );
    expect(getWorkspaceApiPrefixes()).not.toContain('/api/v1/auth');
    expect(getWorkspaceApiPrefixes()).not.toContain('/api/v1/community');
    expect(getWorkspaceApiPrefixes()).not.toContain('/api/v1/qna');
  });

  it('rewrites new app APIs when their manifest contributes a workspace prefix', () => {
    const policy = createWorkspaceApiRoutePolicy({
      platformPrefixes: [],
      sources: [
        {
          contract: {
            workspaceApiPrefixes: ['/api/v1/custom-app'],
          },
        },
      ],
    });

    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/custom-app/resources',
        'hq',
        policy,
      ),
    ).toBe('/api/v1/workspaces/hq/custom-app/resources');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/pms/issues', 'hq', policy),
    ).toBe('/api/v1/pms/issues');
  });

  it('requires a path segment boundary for prefix matches', () => {
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/search-preview/query', 'hq'),
    ).toBe('/api/v1/search-preview/query');
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/wiki-public/pages', 'hq'),
    ).toBe('/api/v1/wiki-public/pages');
  });

  it('preserves intentionally public shared-link endpoints', () => {
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/docs/shared-links/share-1',
        'hq',
      ),
    ).toBe('/api/v1/docs/shared-links/share-1');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/whiteboard/shared-links/share-1',
        'hq',
      ),
    ).toBe('/api/v1/whiteboard/shared-links/share-1');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/docs/pages/page-1?share_token=share-1',
        'hq',
      ),
    ).toBe('/api/v1/docs/pages/page-1?share_token=share-1');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/docs/items/item-1/pages?share_token=share-1',
        'hq',
      ),
    ).toBe('/api/v1/docs/items/item-1/pages?share_token=share-1');
  });

  it('does not let share tokens bypass workspace scoping for other app APIs', () => {
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/pms/issues?share_token=share-1',
        'hq',
      ),
    ).toBe('/api/v1/workspaces/hq/pms/issues?share_token=share-1');
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/search/query?share_token=share-1',
        'hq',
      ),
    ).toBe('/api/v1/workspaces/hq/search/query?share_token=share-1');
  });

  it('preserves paths that are already scoped or not workspace API paths', () => {
    expect(
      rewriteWorkspaceApiPathForWorkspace(
        '/api/v1/workspaces/hq/docs/hub',
        'demo',
      ),
    ).toBe('/api/v1/workspaces/hq/docs/hub');
    expect(rewriteWorkspaceApiPathForWorkspace('/api/v1/auth/me', 'hq')).toBe(
      '/api/v1/auth/me',
    );
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/qna/documents', 'hq'),
    ).toBe('/api/v1/qna/documents');
    expect(
      rewriteWorkspaceApiPathForWorkspace('https://api.test/api/v1/docs', 'hq'),
    ).toBe('https://api.test/api/v1/docs');
    expect(rewriteWorkspaceApiPathForWorkspace('/healthz', 'hq')).toBe(
      '/healthz',
    );
  });

  it('requires a workspace slug and URL-encodes the workspace segment', () => {
    expect(rewriteWorkspaceApiPathForWorkspace('/api/v1/docs/hub', null)).toBe(
      '/api/v1/docs/hub',
    );
    expect(rewriteWorkspaceApiPathForWorkspace('/api/v1/docs/hub', '')).toBe(
      '/api/v1/docs/hub',
    );
    expect(
      rewriteWorkspaceApiPathForWorkspace('/api/v1/docs/hub', 'team space'),
    ).toBe('/api/v1/workspaces/team%20space/docs/hub');
  });
});
