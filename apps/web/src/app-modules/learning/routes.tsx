import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';
import { LearningCourseView } from './views/LearningCourseView';
import { LearningView } from './views/LearningView';

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
