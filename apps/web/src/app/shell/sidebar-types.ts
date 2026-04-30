import type { ReactNode } from 'react';
import type { NavigateFunction } from 'react-router-dom';
import type { LucideIcon } from 'lucide-react';

import type { AuthUser } from '@/src/platform/auth/auth-api';
import type { AppModuleId, NavItem } from './navigation-types';

export interface AppSidebarActionContext {
  currentPathname: string;
  currentWorkspaceSlug: string | null;
  navigate: NavigateFunction;
  user: AuthUser | null;
}

export interface AppSidebarCreateAction {
  id: string;
  label: string;
  icon: LucideIcon;
  run: (context: AppSidebarActionContext) => void;
}

export interface AppSidebarRenderContext extends AppSidebarActionContext {
  activeAppId: AppModuleId;
  activeNavItemId: string;
  canReadWorkspace: boolean;
  filteredItems: NavItem[];
  isCategoryExpanded: (category: string) => boolean;
  toggleCategory: (category: string) => void;
}

export interface AppSidebarConfig {
  createActions?: (
    context: AppSidebarActionContext,
  ) => AppSidebarCreateAction[];
  extendCategories?: (
    categories: string[],
    context: { canReadWorkspace: boolean },
  ) => string[];
  beforeCategories?: (context: AppSidebarRenderContext) => ReactNode;
  afterCategories?: (context: AppSidebarRenderContext) => ReactNode;
  renderCategory?: (
    category: string,
    context: AppSidebarRenderContext,
  ) => ReactNode | undefined;
}
