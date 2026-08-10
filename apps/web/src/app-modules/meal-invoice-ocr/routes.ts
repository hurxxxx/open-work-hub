import { createElement, lazy } from 'react';

import { lazyRoute } from '@/src/app/shell/lazy-route';
import type { WorkspaceRouteDefinition } from '@/src/app/shell/route-types';

const MealInvoiceOcrView = lazy(() =>
  import('./views/MealInvoiceOcrView').then((module) => ({
    default: module.MealInvoiceOcrView,
  })),
);

export const mealInvoiceOcrWorkspaceRoutes: WorkspaceRouteDefinition[] = [
  {
    appId: 'meal-invoice-ocr',
    chrome: 'fullSurface',
    path: '/w/:workspaceSlug/meal-invoice-ocr',
    element: lazyRoute(createElement(MealInvoiceOcrView)),
  },
];
