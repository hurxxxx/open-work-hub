import { useId, useReducer } from 'react';
import { FolderOpen } from 'lucide-react';
import { InlineNotice } from '@ai-do/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  FORM_FIELD_CONTROL_CLASS_NAME,
  FormDialog,
  FormFieldRow,
} from '@/src/components/form/FormDialog';
import { createFolder, type PmsFolder } from '../api/pms-api';
import {
  canSubmitCreateName,
  createFolderPayload,
  INITIAL_PMS_CREATE_MODAL_STATE,
  pmsCreateModalReducer,
} from './pms-create-modal-model';

export const CreateFolderModal = ({
  isOpen,
  onClose,
  teamId,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  teamId: string;
  onCreated?: (folder: PmsFolder) => void;
}) => {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const nameInputId = useId();
  const [{ error, name, submitting }, dispatch] = useReducer(
    pmsCreateModalReducer,
    INITIAL_PMS_CREATE_MODAL_STATE,
  );

  function handleClose() {
    dispatch({ type: 'reset' });
    onClose();
  }

  async function handleCreate() {
    if (!token || !canSubmitCreateName(name)) return;
    dispatch({ type: 'submit' });
    try {
      const folder = await createFolder(
        token,
        createFolderPayload({ name, teamId }),
      );
      onCreated?.(folder);
      handleClose();
    } catch (err) {
      dispatch({
        type: 'failed',
        message:
          err instanceof Error ? err.message : t('apps:pms.createFolderFailed'),
      });
    } finally {
      dispatch({ type: 'finished' });
    }
  }

  return (
    <FormDialog
      cancelLabel={t('common:actions.cancel')}
      closeLabel={t('common:actions.close')}
      open={isOpen}
      onCancel={handleClose}
      onPrimary={() => void handleCreate()}
      title={t('apps:pms.createFolder')}
      maxWidth="max-w-lg"
      primaryDisabled={!canSubmitCreateName(name)}
      primaryLabel={t('apps:pms.createFolder')}
      primaryPendingLabel={t('apps:pms.creating')}
      submitting={submitting}
    >
      <div className="space-y-5 text-app-ink">
        <div className="flex items-center gap-3 p-4 rounded-lg bg-app-surface-sidebar border border-app-border">
          <div className="flex size-10 items-center justify-center rounded-lg bg-app-warning/20">
            <FolderOpen size={20} className="text-app-warning-text" />
          </div>
          <div className="app-text-body text-app-ink/60">
            {t('apps:pms.createFolderDescription')}
          </div>
        </div>

        {error && (
          <InlineNotice role="alert" tone="danger">
            {error}
          </InlineNotice>
        )}

        <FormFieldRow htmlFor={nameInputId} label={t('apps:pms.folderName')}>
          <input
            id={nameInputId}
            type="text"
            placeholder={t('apps:pms.folderPlaceholder')}
            value={name}
            onChange={(event) =>
              dispatch({
                type: 'name',
                value: event.target.value,
              })
            }
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                !event.nativeEvent.isComposing &&
                canSubmitCreateName(name) &&
                !submitting
              ) {
                void handleCreate();
              }
            }}
            className={FORM_FIELD_CONTROL_CLASS_NAME}
          />
        </FormFieldRow>
      </div>
    </FormDialog>
  );
};
