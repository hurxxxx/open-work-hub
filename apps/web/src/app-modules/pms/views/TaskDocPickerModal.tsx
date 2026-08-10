import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DocsHubPickerModal,
  type DocsHubItem,
  buildPmsTaskDocsHubPickerAdapter,
  pickDocsHubSelectionItem,
  resolveDocsHubPickerExcludeDocIds,
} from '@/src/app-modules/docs/public-api';

interface TaskDocPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (doc: DocsHubItem) => Promise<void> | void;
  excludeDocIds?: string[];
  workspaceSlug?: string | null;
}

export function TaskDocPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeDocIds,
  workspaceSlug = null,
}: TaskDocPickerModalProps) {
  const { t } = useTranslation('apps');
  const adapter = useMemo(
    () => buildPmsTaskDocsHubPickerAdapter(t),
    [t],
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
