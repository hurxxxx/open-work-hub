import { workspaceRoleAllows } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import { resolveShellWorkspaceSlug } from '@/src/platform/workspaces/workspace-utils';

export function useSysPerfWorkspace() {
  const { token, user } = useAuth();
  const workspaceBootstrap = useWorkspaceBootstrapContext();
  const workspaceSlug =
    workspaceBootstrap.data?.workspace.slug ??
    resolveShellWorkspaceSlug(user, null);
  const workspaceRole =
    workspaceBootstrap.data?.workspace.role ??
    user?.workspaces.find((workspace) => workspace.slug === workspaceSlug)
      ?.role ??
    null;

  return { token, workspaceSlug, workspaceRole };
}

export function useCanManageSysPerfBase() {
  const { workspaceRole } = useSysPerfWorkspace();
  return workspaceRoleAllows(workspaceRole, 'admin');
}
