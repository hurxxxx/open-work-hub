import { createElement, lazy, Suspense } from 'react';

import type { WhiteboardContextSlotPanelProps } from './views/WhiteboardContextSlotPanel';
import type { WhiteboardEditorSurfaceProps } from './views/WhiteboardEditorSurface';
import type { WhiteboardPickerModalProps } from './views/WhiteboardPickerModal';

export * from './api/whiteboard-api';
export type {
  WhiteboardContextRef,
  WhiteboardContextSlotPanelProps,
} from './views/WhiteboardContextSlotPanel';
export type { WhiteboardEditorSurfaceProps } from './views/WhiteboardEditorSurface';
export type { WhiteboardPickerModalProps } from './views/WhiteboardPickerModal';

const LazyWhiteboardContextSlotPanel = lazy(() =>
  import('./views/WhiteboardContextSlotPanel').then((module) => ({
    default: module.WhiteboardContextSlotPanel,
  })),
);

const LazyWhiteboardEditorSurface = lazy(() =>
  import('./views/WhiteboardEditorSurface').then((module) => ({
    default: module.WhiteboardEditorSurface,
  })),
);

const LazyWhiteboardPickerModal = lazy(() =>
  import('./views/WhiteboardPickerModal').then((module) => ({
    default: module.WhiteboardPickerModal,
  })),
);

export function WhiteboardContextSlotPanel(
  props: WhiteboardContextSlotPanelProps,
) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyWhiteboardContextSlotPanel, props),
  );
}

export function WhiteboardEditorSurface(props: WhiteboardEditorSurfaceProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyWhiteboardEditorSurface, props),
  );
}

export function WhiteboardPickerModal(props: WhiteboardPickerModalProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyWhiteboardPickerModal, props),
  );
}
