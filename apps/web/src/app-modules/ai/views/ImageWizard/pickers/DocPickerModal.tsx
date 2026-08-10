import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DocsHubPickerModal,
  type DocsHubItem,
  buildImageWizardDocsHubPickerAdapter,
  pickDocsHubSelectionItem,
  resolveDocsHubPickerExcludeDocIds,
} from '@/src/app-modules/docs/public-api';

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
  const { t } = useTranslation('apps');
  const adapter = useMemo(
    () => buildImageWizardDocsHubPickerAdapter(t),
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
