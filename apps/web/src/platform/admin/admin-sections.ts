import { defineCoreAdminSections } from '@open-work-hub/core-web/admin';

export const ADMIN_SECTION_DEFINITIONS = defineCoreAdminSections([
  { id: 'general', path: '/admin/general', roles: ['platform_admin'] },
  { id: 'apps', path: '/admin/apps/platform', roles: ['platform_admin'] },
  { id: 'llm', path: '/admin/llm', roles: ['platform_admin'] },
  {
    id: 'model-monitoring',
    path: '/admin/model-monitoring',
    roles: ['platform_admin'],
  },
  {
    id: 'document-processing',
    path: '/admin/document-processing',
    roles: ['platform_admin'],
  },
  { id: 'ai-security', path: '/admin/ai-security', roles: ['platform_admin'] },
  { id: 'workspaces', path: '/admin/workspaces', roles: ['platform_admin'] },
  { id: 'community', path: '/admin/community', roles: ['platform_admin'] },
  { id: 'usage', path: '/admin/usage', roles: ['platform_admin'] },
  { id: 'audit', path: '/admin/audit', roles: ['platform_admin'] },
] as const);

export type AdminSection = (typeof ADMIN_SECTION_DEFINITIONS)[number]['id'];
