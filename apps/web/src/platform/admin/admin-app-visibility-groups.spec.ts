import { describe, expect, it } from 'vitest';

import type { AdminAppBarCategory } from './admin-api';
import {
  buildAppVisibilityGroups,
  partitionAppVisibilityItems,
  PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID,
  UNCATEGORIZED_APP_VISIBILITY_GROUP_ID,
  type AppVisibilityGroupableItem,
} from './admin-app-visibility-groups';

interface TestVisibilityItem extends AppVisibilityGroupableItem {
  route_base: string;
}

function item(
  app_id: string,
  title: string,
  kind = 'mode',
): TestVisibilityItem {
  return {
    app_id,
    kind,
    route_base: `/${app_id}`,
    title,
  };
}

function category(
  id: string,
  title: string,
  appIds: string[],
): AdminAppBarCategory {
  return {
    icon_key: 'layout',
    id,
    items: appIds.map((app_id) => ({
      app_id,
      coming_soon: false,
      icon_key: 'layout',
      route_base: `/${app_id}`,
      runtime_enabled: true,
      title: app_id,
    })),
    key: id,
    position: 0,
    title,
  };
}

describe('buildAppVisibilityGroups', () => {
  it('keeps launcher apps uncategorized when dynamic categories are unavailable', () => {
    const groups = buildAppVisibilityGroups([
      item('home', 'Home'),
      item('business', 'Business'),
      item('retrieval-search', 'Retrieval', 'launcher_app'),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.id).toBe(UNCATEGORIZED_APP_VISIBILITY_GROUP_ID);
    expect(groups[0]?.rows.map((row) => row.app_id)).toEqual([
      'retrieval-search',
    ]);
  });

  it('uses app bar categories as visibility groups, including empty custom categories', () => {
    const groups = buildAppVisibilityGroups(
      [
        item('home', 'Home'),
        item('ai', 'AI'),
        item('business', 'Business'),
        item('retrieval-search', 'Retrieval', 'launcher_app'),
        item('law-search', 'Law search', 'launcher_app'),
      ],
      [
        category('business-tools', 'Business tools', ['law-search']),
        category('lab', 'Lab', ['retrieval-search']),
        category('empty', 'Empty category', []),
      ],
    );

    expect(groups.map((group) => [group.title, group.rows.length])).toEqual([
      ['Business tools', 1],
      ['Lab', 1],
      ['Empty category', 0],
    ]);
    expect(groups[1]?.rows.map((row) => row.app_id)).toEqual([
      'retrieval-search',
    ]);
    expect(
      groups.some(
        (group) => group.id === UNCATEGORIZED_APP_VISIBILITY_GROUP_ID,
      ),
    ).toBe(false);
  });

  it('selects launcher apps by kind even without a static parent id', () => {
    const groups = buildAppVisibilityGroups([
      item('legacy-mode', 'Legacy mode'),
      item('uncategorized-app', 'Uncategorized app', 'launcher_app'),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0]?.rows.map((row) => row.app_id)).toEqual([
      'uncategorized-app',
    ]);
  });

  it('shows fixed personal tools separately from configurable app bar groups', () => {
    const mail = {
      ...item('mail', 'Mail', 'launcher_app'),
      launcher_personal_tools: true,
    };
    const planner = {
      ...item('planner', 'Planner', 'launcher_app'),
      launcher_personal_tools: true,
    };
    const groups = buildAppVisibilityGroups(
      [mail, planner, item('docs', 'Docs', 'launcher_app')],
      [category('collaboration', 'Collaboration', ['docs'])],
    );

    expect(groups.map((group) => group.id)).toEqual([
      'app-bar:collaboration',
      PERSONAL_TOOLS_APP_VISIBILITY_GROUP_ID,
    ]);
    expect(groups[1]?.rows.map((row) => row.app_id)).toEqual([
      'mail',
      'planner',
    ]);
  });
});

describe('partitionAppVisibilityItems', () => {
  it('separates fixed personal tools from company apps by registry metadata', () => {
    const mail = {
      ...item('mail', 'Mail', 'launcher_app'),
      launcher_personal_tools: true,
    };
    const planner = {
      ...item('planner', 'Planner', 'launcher_app'),
      launcher_personal_tools: true,
    };
    const docs = item('docs', 'Docs', 'launcher_app');
    const community = item('community', 'Community', 'launcher_app');

    const result = partitionAppVisibilityItems([
      docs,
      mail,
      community,
      planner,
    ]);

    expect(result.configurableApps.map((entry) => entry.app_id)).toEqual([
      'docs',
      'community',
    ]);
    expect(result.personalTools.map((entry) => entry.app_id)).toEqual([
      'mail',
      'planner',
    ]);
  });
});
