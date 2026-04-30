import { GraduationCap } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const learningManifest: AppModuleManifest = {
  appBarItem: { id: 'learning', title: '학습', icon: GraduationCap },
  defaultActiveNavItemId: 'learning-home',
  navItems: [
    { id: 'learning-home', title: '전체 학습 홈', icon: GraduationCap, category: 'Courses', appId: 'learning', description: '모든 구성원이 열람할 수 있는 교육 콘텐츠 모음' },
  ],
  workspaceRoutePaths: [
    '/w/:workspaceSlug/learning',
    '/w/:workspaceSlug/learning/:courseSlug',
    '/w/:workspaceSlug/learning/:courseSlug/:lessonSlug',
  ],
};
