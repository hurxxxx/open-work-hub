import { Navigate } from 'react-router-dom';

import {
  getDefaultAdminPath as getPlatformDefaultAdminPath,
  type DefaultAdminPathResolver,
} from '@/src/platform/admin/admin-permissions';
import { useAuth } from '@/src/platform/auth/auth-provider';

export function AdminLandingRedirect({
  getDefaultAdminPath = getPlatformDefaultAdminPath,
}: {
  getDefaultAdminPath?: DefaultAdminPathResolver;
}) {
  const auth = useAuth();

  if (!auth.user) {
    return <Navigate replace to="/login" />;
  }

  return <Navigate replace to={getDefaultAdminPath(auth.user.system_roles)} />;
}
