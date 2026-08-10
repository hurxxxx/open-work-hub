export const LEGACY_ISSUE_DEFAULT_DATASET_KEY = 'common-master' as const;
export const LEGACY_ISSUE_ASSISTANT_NAV_ITEM_ID = 'legacy-issues-assistant';
export const LEGACY_ISSUE_ASSISTANT_HISTORY_NAV_ITEM_ID =
  'legacy-issues-assistant-history';
export const LEGACY_ISSUE_FIELD_SETTINGS_NAV_ITEM_ID =
  'legacy-issues-field-settings';
export const LEGACY_ISSUE_COMMON_CODE_NAV_ITEM_ID = 'legacy-issues-common-code';
export const LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID =
  'legacy-issues-direct-edit-permissions';
export const LEGACY_ISSUE_VEHICLE_CHECKLISTS_NAV_ITEM_ID =
  'legacy-issues-vehicle-checklists';
export const LEGACY_ISSUE_VEHICLE_MANAGEMENT_NAV_ITEM_ID =
  'legacy-issues-vehicle-management';
export const LEGACY_ISSUE_ASSISTANT_PATH_SUFFIX = '/assistant';
export const LEGACY_ISSUE_ASSISTANT_HISTORY_PATH_SUFFIX = '/assistant/history';
export const LEGACY_ISSUE_REPORTS_PATH_SUFFIX = '/reports';
export const LEGACY_ISSUE_FIELD_SETTINGS_PATH_SUFFIX = '/settings/fields';
export const LEGACY_ISSUE_COMMON_CODE_PATH_SUFFIX = '/settings/common-codes';
export const LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_PATH_SUFFIX =
  '/settings/direct-edit-permissions';
export const LEGACY_ISSUE_VEHICLE_CHECKLISTS_PATH_SUFFIX =
  '/vehicle-checklists';
export const LEGACY_ISSUE_VEHICLE_MANAGEMENT_PATH_SUFFIX =
  '/settings/vehicle-models';
export const LEGACY_ISSUE_ASSISTANT_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/assistant';
export const LEGACY_ISSUE_ASSISTANT_HISTORY_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/assistant/history';
export const LEGACY_ISSUE_REPORTS_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/reports';
export const LEGACY_ISSUE_REPORT_DETAIL_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/reports/:reportNumber';
export const LEGACY_ISSUE_FIELD_SETTINGS_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/settings/fields';
export const LEGACY_ISSUE_COMMON_CODE_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/settings/common-codes';
export const LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/settings/direct-edit-permissions';
export const LEGACY_ISSUE_VEHICLE_CHECKLISTS_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/vehicle-checklists';
export const LEGACY_ISSUE_VEHICLE_CHECKLIST_DETAIL_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/vehicle-checklists/:vehicleModelId';
export const LEGACY_ISSUE_VEHICLE_CHECKLIST_MODULE_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/vehicle-checklists/:vehicleModelId/:moduleKey';
export const LEGACY_ISSUE_VEHICLE_MANAGEMENT_ROUTE_PATH =
  '/w/:workspaceSlug/legacy-issues/settings/vehicle-models';
export const LEGACY_ISSUE_ASSISTANT_SCOPE_REF = 'legacy_issues';
export const LEGACY_ISSUE_ASSISTANT_SCOPE_RESOURCE_ID = 'workspace';

export const LEGACY_ISSUE_DATASET_KEYS = [
  LEGACY_ISSUE_DEFAULT_DATASET_KEY,
] as const;

export type LegacyIssueDatasetKey = (typeof LEGACY_ISSUE_DATASET_KEYS)[number];
export const LEGACY_ISSUE_DEFAULT_VIEW_KEY = 'common-master' as const;
export const LEGACY_ISSUE_MODULE_VIEW_KEYS = [
  'aircon',
  'heat-exchanger',
  'compressor-mechanical',
  'compressor-electric',
  'interior',
  'cooling-module',
  'electrical-mechanical',
  'electrical-control-hw',
  'electrical-control-sw',
] as const;
export const LEGACY_ISSUE_VIEW_KEYS = [
  LEGACY_ISSUE_DEFAULT_VIEW_KEY,
  ...LEGACY_ISSUE_MODULE_VIEW_KEYS,
] as const;
export type LegacyIssueViewKey = (typeof LEGACY_ISSUE_VIEW_KEYS)[number];
export type LegacyIssueModuleViewKey =
  (typeof LEGACY_ISSUE_MODULE_VIEW_KEYS)[number];

export interface LegacyIssueDatasetDefinition {
  key: LegacyIssueDatasetKey;
  navItemId: string;
  pathSuffix: string;
  routePath: string;
  gridLayoutId: string;
}

export interface LegacyIssueViewDefinition {
  key: LegacyIssueViewKey;
  datasetKey: LegacyIssueDatasetKey;
  navItemId: string;
  parentNavCategoryId?: string;
  pathSuffix: string;
  routePath: string;
  gridLayoutId: string;
}

export const LEGACY_ISSUE_DATASETS = {
  'common-master': {
    key: 'common-master',
    navItemId: 'legacy-issues-common-master',
    pathSuffix: '/common-master',
    routePath: '/w/:workspaceSlug/legacy-issues/common-master',
    gridLayoutId: 'legacy-issues.common-master.grid',
  },
} as const satisfies Record<
  LegacyIssueDatasetKey,
  LegacyIssueDatasetDefinition
>;

export const LEGACY_ISSUE_VIEWS = {
  'common-master': {
    key: 'common-master',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-common-master',
    pathSuffix: '/common-master',
    routePath: '/w/:workspaceSlug/legacy-issues/common-master',
    gridLayoutId: 'legacy-issues.common-master.grid',
  },
  aircon: {
    key: 'aircon',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-aircon',
    pathSuffix: '/aircon',
    routePath: '/w/:workspaceSlug/legacy-issues/aircon',
    gridLayoutId: 'legacy-issues.aircon.grid',
  },
  'heat-exchanger': {
    key: 'heat-exchanger',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-heat-exchanger',
    pathSuffix: '/heat-exchanger',
    routePath: '/w/:workspaceSlug/legacy-issues/heat-exchanger',
    gridLayoutId: 'legacy-issues.heat-exchanger.grid',
  },
  'compressor-mechanical': {
    key: 'compressor-mechanical',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-compressor-mechanical',
    parentNavCategoryId: 'legacy-issues-compressor',
    pathSuffix: '/compressor/mechanical',
    routePath: '/w/:workspaceSlug/legacy-issues/compressor/mechanical',
    gridLayoutId: 'legacy-issues.compressor-mechanical.grid',
  },
  'compressor-electric': {
    key: 'compressor-electric',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-compressor-electric',
    parentNavCategoryId: 'legacy-issues-compressor',
    pathSuffix: '/compressor/electric',
    routePath: '/w/:workspaceSlug/legacy-issues/compressor/electric',
    gridLayoutId: 'legacy-issues.compressor-electric.grid',
  },
  interior: {
    key: 'interior',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-interior',
    pathSuffix: '/interior',
    routePath: '/w/:workspaceSlug/legacy-issues/interior',
    gridLayoutId: 'legacy-issues.interior.grid',
  },
  'cooling-module': {
    key: 'cooling-module',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-cooling-module',
    pathSuffix: '/cooling-module',
    routePath: '/w/:workspaceSlug/legacy-issues/cooling-module',
    gridLayoutId: 'legacy-issues.cooling-module.grid',
  },
  'electrical-mechanical': {
    key: 'electrical-mechanical',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-electrical-mechanical',
    parentNavCategoryId: 'legacy-issues-electrical',
    pathSuffix: '/electrical/mechanical',
    routePath: '/w/:workspaceSlug/legacy-issues/electrical/mechanical',
    gridLayoutId: 'legacy-issues.electrical-mechanical.grid',
  },
  'electrical-control-hw': {
    key: 'electrical-control-hw',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-electrical-control-hw',
    parentNavCategoryId: 'legacy-issues-electrical',
    pathSuffix: '/electrical/control/hw',
    routePath: '/w/:workspaceSlug/legacy-issues/electrical/control/hw',
    gridLayoutId: 'legacy-issues.electrical-control-hw.grid',
  },
  'electrical-control-sw': {
    key: 'electrical-control-sw',
    datasetKey: 'common-master',
    navItemId: 'legacy-issues-electrical-control-sw',
    parentNavCategoryId: 'legacy-issues-electrical',
    pathSuffix: '/electrical/control/sw',
    routePath: '/w/:workspaceSlug/legacy-issues/electrical/control/sw',
    gridLayoutId: 'legacy-issues.electrical-control-sw.grid',
  },
} as const satisfies Record<LegacyIssueViewKey, LegacyIssueViewDefinition>;
