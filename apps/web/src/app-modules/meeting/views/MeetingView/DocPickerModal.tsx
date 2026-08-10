import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DocsHubPickerModal,
  type DocsHubItem,
  buildMeetingDocsHubPickerAdapter,
  pickDocsHubSelectionItem,
  resolveDocsHubPickerExcludeDocIds,
} from '@/src/app-modules/docs/public-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { normalizeTimeZone } from '@/src/platform/time/time-utils';

interface DocPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (doc: DocsHubItem) => Promise<void> | void;
  excludeDocIds?: string[];
  workspaceSlug: string;
}

export function DocPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeDocIds,
  workspaceSlug,
}: DocPickerModalProps) {
  const { t, i18n } = useTranslation('apps');
  const { user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const adapter = useMemo(
    () => buildMeetingDocsHubPickerAdapter({
      locale: i18n.language,
      t,
      timeZone,
    }),
    [i18n.language, t, timeZone],
  );

  return (
    <DocsHubPickerModal
      isOpen={isOpen}
      onClose={onClose}
      workspaceSlug={workspaceSlug}
      excludeDocIds={resolveDocsHubPickerExcludeDocIds(excludeDocIds)}
      adapter={adapter}
      onPick={pickDocsHubSelectionItem(onPick)}
    />
  );
}
