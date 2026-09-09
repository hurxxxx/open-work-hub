import { createElement, lazy, Suspense } from 'react';

import { meetingManifest } from './manifest';
import { meetingAppRoutes } from './routes';
import { meetingSidebarConfig } from './sidebar';
import type { MeetingCreateModalProps } from './views/MeetingView/MeetingCreateModal';
import type { MeetingDetailLayoutProps } from './views/MeetingView/MeetingDetailLayout';

export { meetingManifest } from './manifest';
export { meetingAppRoutes } from './routes';
export { meetingSidebarConfig } from './sidebar';
export type { MeetingCreateModalProps } from './views/MeetingView/MeetingCreateModal';
export type { MeetingDetailLayoutProps } from './views/MeetingView/MeetingDetailLayout';

const LazyMeetingCreateModal = lazy(() =>
  import('./views/MeetingView/MeetingCreateModal').then((module) => ({
    default: module.MeetingCreateModal,
  })),
);

const LazyMeetingDetailLayout = lazy(() =>
  import('./views/MeetingView/MeetingDetailLayout').then((module) => ({
    default: module.MeetingDetailLayout,
  })),
);

export function MeetingCreateModal(props: MeetingCreateModalProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyMeetingCreateModal, props),
  );
}

export function MeetingDetailLayout(props: MeetingDetailLayoutProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyMeetingDetailLayout, props),
  );
}

export const meetingModule = {
  manifest: meetingManifest,
  sidebarConfig: meetingSidebarConfig,
  appRoutes: meetingAppRoutes,
} as const;
