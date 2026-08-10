import { CalendarDays, Clock, Plane, Timer, Users } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

// 기본 비활성·숨김 상태인 개인근태 UI 프로토타입. 서버 API와 쓰기 기능은 없다.
// 앱바 노출·배치는 백엔드 app_catalog(personal-attendance)가 담당한다.
export const personalAttendanceManifest: AppModuleManifest = {
  appBarItem: {
    id: 'personal-attendance',
    title: 'personal-attendance',
    icon: Clock,
  },
  surfaces: { launcher: { globalPath: '/personal-attendance' } },
  contract: {
    owner: 'commute-platform',
    permissions: [],
    apiDomain: null,
    resourceScope: 'personal',
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: [
      'apps/web/src/app-modules/personal-attendance/api/personal-attendance-api.spec.ts',
      'apps/web/src/app-modules/personal-attendance/lib/attendance-format.spec.ts',
      'apps/web/src/app-modules/personal-attendance/lib/attendance-labels.spec.ts',
    ],
  },
  defaultActiveNavItemId: 'personal-attendance-overview',
  navItems: [
    {
      id: 'personal-attendance-overview',
      title: 'personal-attendance-overview',
      icon: CalendarDays,
      category: 'attendance',
      appId: 'personal-attendance',
    },
    {
      id: 'personal-attendance-overtime',
      title: 'personal-attendance-overtime',
      icon: Timer,
      category: 'attendance-requests',
      appId: 'personal-attendance',
      pathSuffix: '?tab=overtime',
    },
    {
      id: 'personal-attendance-leave',
      title: 'personal-attendance-leave',
      icon: Plane,
      category: 'attendance-requests',
      appId: 'personal-attendance',
      pathSuffix: '?tab=leave',
    },
    {
      id: 'personal-attendance-holiday',
      title: 'personal-attendance-holiday',
      icon: Users,
      category: 'attendance-requests',
      appId: 'personal-attendance',
      pathSuffix: '?tab=holiday',
    },
    {
      id: 'personal-attendance-flex',
      title: 'personal-attendance-flex',
      icon: Clock,
      category: 'attendance-requests',
      appId: 'personal-attendance',
      pathSuffix: '?tab=flex',
    },
  ],
  workspaceRoutePaths: [],
  globalRoutePaths: ['/personal-attendance'],
};
