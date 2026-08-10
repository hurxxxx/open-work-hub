import { Receipt } from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const mealInvoiceOcrManifest: AppModuleManifest = {
  appBarItem: {
    id: 'meal-invoice-ocr',
    title: 'meal-invoice-ocr',
    icon: Receipt,
  },
  contract: {
    owner: 'business-app',
    permissions: [],
    apiDomain: 'meal_invoice_ocr',
    workspaceApiPrefixes: ['/api/v1/meal-invoice-ocr'],
    aiCapabilities: [],
    writeAuditActions: [],
    appLocalTests: ['apps/api/tests/test_meal_invoice_ocr.py'],
  },
  defaultActiveNavItemId: 'meal-invoice-ocr',
  navItems: [
    {
      id: 'meal-invoice-ocr',
      title: 'meal-invoice-ocr',
      icon: Receipt,
      category: 'Business',
      appId: 'meal-invoice-ocr',
      description: 'meal-invoice-ocr',
    },
  ],
  workspaceRoutePaths: ['/w/:workspaceSlug/meal-invoice-ocr'],
};
