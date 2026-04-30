import { LearningCourseView } from '@/src/components/views/LearningCourseView';
import { LearningView } from '@/src/components/views/LearningView';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

export const learningWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'learning',
    path: '/w/:workspaceSlug/learning',
    element: <LearningView />,
  },
  {
    appId: 'learning',
    path: '/w/:workspaceSlug/learning/:courseSlug',
    element: <LearningCourseView />,
  },
  {
    appId: 'learning',
    path: '/w/:workspaceSlug/learning/:courseSlug/:lessonSlug',
    element: <LearningCourseView />,
  },
];
