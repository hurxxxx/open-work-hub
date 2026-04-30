import type { ReactNode } from 'react';
import { useParams } from 'react-router-dom';

import {
  hasAdminSectionAccess,
  type AdminSection,
} from '@/src/domains/admin/admin-permissions';
import {
  hasAdminConsoleAccess,
  hasWorkspaceMembership,
} from '@/src/domains/auth/auth-api';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { AccessDeniedView } from '@/src/domains/auth/settings-pages';

export function WorkspaceGate({
  children,
  appId,
  bootstrapAppIds,
  bootstrapError,
  bootstrapLoading,
}: {
  children: ReactNode;
  appId: string;
  bootstrapAppIds: string[] | null;
  bootstrapError: string | null;
  bootstrapLoading: boolean;
}) {
  const auth = useAuth();
  const { workspaceSlug } = useParams();

  if (!hasWorkspaceMembership(auth.user, workspaceSlug)) {
    return (
      <AccessDeniedView description="현재 계정은 이 workspace에서 해당 앱을 사용할 수 없습니다." />
    );
  }

  if (workspaceSlug) {
    if (bootstrapLoading || bootstrapAppIds === null) {
      return <div className="p-8 text-gray-500">워크스페이스 구성을 불러오는 중입니다.</div>;
    }
    if (bootstrapError) {
      return <AccessDeniedView description={bootstrapError} />;
    }
    if (!bootstrapAppIds.includes(appId)) {
      return (
        <AccessDeniedView description="현재 workspace에서는 이 앱이 활성화되어 있지 않습니다." />
      );
    }
  }

  return children;
}

export function AdminGate({
  section,
  children,
}: {
  section: AdminSection;
  children: ReactNode;
}) {
  const auth = useAuth();
  if (!hasAdminConsoleAccess(auth.user) || !hasAdminSectionAccess(auth.user?.system_roles ?? [], section)) {
    return <AccessDeniedView description="현재 계정에는 이 관리자 섹션을 볼 권한이 없습니다." />;
  }

  return children;
}
