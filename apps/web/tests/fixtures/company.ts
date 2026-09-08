import { APP_CONTRACTS } from '@open-work-hub/contracts/app-contracts';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type {
  AppsBootstrapResponse,
  BootstrapApp,
} from '@/src/platform/apps/apps-api';

export function createAuthUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    id: 'user-1',
    login_id: 'member',
    email: 'member@example.test',
    full_name: 'Member',
    display_name: 'Member',
    employee_code: null,
    job_title: null,
    primary_organization_unit: null,
    status: 'active',
    login_blocked: false,
    theme_preference: 'system',
    locale: 'ko-KR',
    time_zone: 'Asia/Seoul',
    date_format: 'korean',
    app_bar_layout: { pinned_app_ids: [] },
    system_roles: [],
    group_ids: [],
    managed_organization_unit_ids: [],
    is_department_head: false,
    must_change_password: false,
    last_login_at: null,
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    ...overrides,
  };
}

export function createBootstrapApp(
  appId: string,
  overrides: Partial<BootstrapApp> = {},
): BootstrapApp {
  const contract = APP_CONTRACTS.find((entry) => entry.app_id === appId);
  return {
    app_id: appId,
    entry_route_id: contract?.entry_route_id ?? `${appId}.root`,
    execution_context_kind: contract?.execution_context_kind ?? 'company',
    resource_scope: contract?.resource_scope ?? 'company',
    route_base: contract?.route_base ?? `/apps/${appId}`,
    title: contract?.title ?? appId,
    icon_key: contract?.icon_key ?? 'box',
    enabled: true,
    coming_soon: false,
    nav_items: [],
    ...overrides,
  };
}

export function createAppsBootstrap(
  overrides: Partial<AppsBootstrapResponse> = {},
): AppsBootstrapResponse {
  return {
    apps: [],
    nav: [],
    app_bar_categories: [],
    personal_tool_app_ids: [],
    chatbot_app_ids: [],
    keyword_search: { entity_types: [] },
    principal: { kind: 'user', source: 'test', user_id: 'user-1' },
    ...overrides,
  };
}
