import { personalAttendanceManifest } from './manifest';
import { personalAttendanceGlobalRoutes } from './routes';

export { personalAttendanceManifest };
export { personalAttendanceGlobalRoutes };

export const personalAttendanceModule = {
  globalRoutes: personalAttendanceGlobalRoutes,
  manifest: personalAttendanceManifest,
} as const;
