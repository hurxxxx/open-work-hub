import {
  FilePenLine,
  Inbox,
  Mail,
  MailOpen,
  Settings,
  Star,
} from 'lucide-react';

import type { AppModuleManifest } from '@/src/app/shell/navigation-types';

export const mailManifest: AppModuleManifest = {
  appBarItem: { id: 'mail', title: 'mail', icon: Mail },
  surfaces: { launcher: { globalPath: '/mail' } },
  contract: {
    owner: 'mail-platform',
    permissions: [],
    apiDomain: 'mail',
    resourceScope: 'personal',
    aiCapabilities: ['mail.list_messages', 'mail.get_message'],
    writeAuditActions: [
      'mail.account.create',
      'mail.account.update',
      'mail.account.delete',
      'mail.draft.send',
    ],
    appLocalTests: [
      'apps/web/src/app-modules/mail/api/mail-api.spec.ts',
      'apps/web/src/app-modules/mail/routes.spec.ts',
      'apps/web/src/app-modules/mail/views/mail-view-model.spec.ts',
      'apps/web/src/app-modules/mail/views/mail-workspace-workflow.spec.ts',
      'apps/web/src/app-modules/mail/views/useMailViewController.spec.ts',
      'apps/api/tests/test_mail_integration.py',
      'apps/api/tests/test_mail_personal_scope.py',
      'apps/worker/tests/test_mail_tasks.py',
    ],
  },
  defaultActiveNavItemId: 'mail-inbox',
  navItems: [
    {
      id: 'mail-inbox',
      title: 'mail-inbox',
      icon: Inbox,
      category: 'Mail',
      appId: 'mail',
    },
    {
      id: 'mail-unread',
      title: 'mail-unread',
      icon: MailOpen,
      category: 'Mail',
      appId: 'mail',
      pathSuffix: '?unread=true',
    },
    {
      id: 'mail-starred',
      title: 'mail-starred',
      icon: Star,
      category: 'Mail',
      appId: 'mail',
      pathSuffix: '?starred=true',
    },
    {
      id: 'mail-drafts',
      title: 'mail-drafts',
      icon: FilePenLine,
      category: 'Mail',
      appId: 'mail',
      pathSuffix: '?view=drafts',
    },
    {
      id: 'mail-settings',
      title: 'mail-settings',
      icon: Settings,
      category: 'Mail',
      appId: 'mail',
      pathSuffix: '?view=settings',
    },
  ],
  workspaceRoutePaths: [],
  globalRoutePaths: ['/mail'],
};
