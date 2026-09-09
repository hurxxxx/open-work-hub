import { defineCoreAdminSections } from '@open-work-hub/core-web/admin';

export const ADMIN_SECTION_DEFINITIONS = defineCoreAdminSections([
  { id: 'general', path: '/admin/general', roles: ['platform_admin'] },
  { id: 'people', path: '/admin/people', roles: ['platform_admin'] },
  {
    id: 'organization',
    path: '/admin/organization',
    roles: ['platform_admin'],
  },
  {
    id: 'api-integrations',
    path: '/admin/api-integrations',
    roles: ['platform_admin'],
  },
  { id: 'apps', path: '/admin/apps/access', roles: ['platform_admin'] },
  { id: 'llm', path: '/admin/llm', roles: ['platform_admin'] },
  { id: 'ai-tools', path: '/admin/ai-tools', roles: ['platform_admin'] },
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
  { id: 'groups', path: '/admin/groups', roles: ['platform_admin'] },
  { id: 'community', path: '/admin/community', roles: ['platform_admin'] },
  { id: 'usage', path: '/admin/usage', roles: ['platform_admin'] },
  { id: 'audit', path: '/admin/audit', roles: ['platform_admin'] },
] as const);

export type AdminSection = (typeof ADMIN_SECTION_DEFINITIONS)[number]['id'];
