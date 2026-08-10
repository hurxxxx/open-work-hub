import { createElement, lazy, Suspense } from 'react';

import type { DocsHubPickerModalProps } from './views/DocsHubPickerModal';
import type {
  DocsEmbeddedViewerProps,
  DocsViewerModalProps,
} from './views/DocsViewerModal';

export * from './api/docs-api';
export * from './api/docs-hub-picker-model';
export * from './api/docs-page-reorder';
export type {
  DocsHubPickerAdapter,
  DocsHubPickerCopy,
  DocsHubPickerModalProps,
} from './views/DocsHubPickerModal';
export {
  EMPTY_DOCS_HUB_PICKER_EXCLUDED_DOC_IDS,
  buildImageWizardDocsHubPickerAdapter,
  buildMeetingDocsHubPickerAdapter,
  buildPmsTaskDocsHubPickerAdapter,
  pickDocsHubSelectionItem,
  resolveDocsHubPickerExcludeDocIds,
} from './views/docs-hub-picker-adapters';
export type {
  DocsEmbeddedViewerProps,
  DocsViewerModalProps,
} from './views/DocsViewerModal';

const LazyDocsHubPickerModal = lazy(() =>
  import('./views/DocsHubPickerModal').then((module) => ({
    default: module.DocsHubPickerModal,
  })),
);

const LazyDocsViewerModal = lazy(() =>
  import('./views/DocsViewerModal').then((module) => ({
    default: module.DocsViewerModal,
  })),
);

const LazyDocsEmbeddedViewer = lazy(() =>
  import('./views/DocsViewerModal').then((module) => ({
    default: module.DocsEmbeddedViewer,
  })),
);

export function DocsHubPickerModal(props: DocsHubPickerModalProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyDocsHubPickerModal, props),
  );
}

export function DocsViewerModal(props: DocsViewerModalProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyDocsViewerModal, props),
  );
}

export function DocsEmbeddedViewer(props: DocsEmbeddedViewerProps) {
  return createElement(
    Suspense,
    { fallback: null },
    createElement(LazyDocsEmbeddedViewer, props),
  );
}
