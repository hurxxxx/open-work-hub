import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  buildPmsTaskDocsHubPickerAdapter,
  DocsHubPickerModal,
  pickDocsHubSelectionItem,
  resolveDocsHubPickerExcludeDocIds,
  type DocsHubItem,
} from '@/src/app-modules/docs/public-api';

interface TaskDocPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (doc: DocsHubItem) => Promise<void> | void;
  excludeDocIds?: string[];
}

export function TaskDocPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeDocIds,
}: TaskDocPickerModalProps) {
  const { t } = useTranslation('apps');
  const adapter = useMemo(() => buildPmsTaskDocsHubPickerAdapter(t), [t]);

  return (
    <DocsHubPickerModal
      isOpen={isOpen}
      onClose={onClose}
      excludeDocIds={resolveDocsHubPickerExcludeDocIds(excludeDocIds)}
      adapter={adapter}
      onPick={pickDocsHubSelectionItem(onPick)}
    />
  );
}
