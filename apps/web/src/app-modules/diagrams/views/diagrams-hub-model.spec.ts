import { describe, expect, it } from 'vitest';

import {
  diagramsHubReducer,
  itemPath,
  readStoredDiagramLayoutMode,
  rootPath,
  viewFromSearch,
  writeStoredDiagramLayoutMode,
} from './diagrams-hub-model';

const user = {
  workspaces: [{ id: 'workspace-1', key: 'lab', slug: 'lab' }],
};

describe('diagrams hub model', () => {
  it('normalizes hub view search values', () => {
    expect(viewFromSearch('mine')).toBe('mine');
    expect(viewFromSearch('archived')).toBe('archived');
    expect(viewFromSearch('trash')).toBe('all');
  });

  it('builds workspace and default workspace paths', () => {
    expect(
      itemPath({ itemId: 'diagram 1', user, workspaceSlug: 'research' }),
    ).toBe('/w/research/diagrams/diagram%201');
    expect(itemPath({ itemId: 'diagram-1', user })).toBe(
      '/w/lab/diagrams/diagram-1',
    );
    expect(rootPath('research', user, new URLSearchParams('view=mine'))).toBe(
      '/w/research/diagrams?view=mine',
    );
  });

  it('stores the layout mode', () => {
    const storage = new Map<string, string>();
    const adapter = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    };

    expect(readStoredDiagramLayoutMode(adapter)).toBe('grid');
    writeStoredDiagramLayoutMode('list', adapter);
    expect(readStoredDiagramLayoutMode(adapter)).toBe('list');
  });

  it('upserts and removes items in reducer state', () => {
    const item = {
      id: 'diagram-1',
      workspace_id: 'workspace-1',
      title: 'Diagram',
      visibility: 'personal',
      version: 1,
      created_by_id: 'user-1',
      created_by_name: 'Ada',
      created_at: '2026-06-28T00:00:00Z',
      updated_at: '2026-06-28T00:00:00Z',
      archived_at: null,
      preview_available: false,
      preview_url: null,
      can_edit: true,
      can_manage: true,
    } as const;

    const loaded = diagramsHubReducer(
      { items: [], loading: true, error: null },
      { type: 'loaded', items: [item] },
    );
    expect(loaded.items).toEqual([item]);
    expect(
      diagramsHubReducer(loaded, { type: 'remove', id: item.id }).items,
    ).toEqual([]);
  });
});
