import { createElement, lazy, Suspense } from 'react';

import type { MeetingCreateModalProps } from './views/MeetingView/MeetingCreateModal';
import type { MeetingWorkspaceLayoutProps } from './views/MeetingView/MeetingWorkspaceLayout';

export { meetingManifest } from './manifest';
export { meetingWorkspaceRoutes } from './routes';
export { meetingSidebarConfig } from './sidebar';
export type { MeetingCreateModalProps } from './views/MeetingView/MeetingCreateModal';
export type { MeetingWorkspaceLayoutProps } from './views/MeetingView/MeetingWorkspaceLayout';

const LazyMeetingCreateModal = lazy(() =>
  import('./views/MeetingView/MeetingCreateModal').then((module) => ({
    default: module.MeetingCreateModal,
  })),
);

const LazyMeetingWorkspaceLayout = lazy(() =>
  import('./views/MeetingView/MeetingWorkspaceLayout').then((module) => ({
    default: module.MeetingWorkspaceLayout,
  })),
);

export function MeetingCreateModal(props: MeetingCreateModalProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyMeetingCreateModal, props),
  );
}

export function MeetingWorkspaceLayout(props: MeetingWorkspaceLayoutProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyMeetingWorkspaceLayout, props),
  );
}
