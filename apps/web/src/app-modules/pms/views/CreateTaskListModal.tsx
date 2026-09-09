import {
  FORM_FIELD_CONTROL_CLASS_NAME,
  FORM_TEXTAREA_CONTROL_CLASS_NAME,
  FormDialog,
  FormFieldRow,
} from '@/src/components/form/FormDialog';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { InlineNotice } from '@open-work-hub/ui';
import { useEffect, useId, useReducer, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { createPmsTaskList, type PmsTaskList } from '../api/pms-api';
import {
  canSubmitCreateName,
  createTaskListPayload,
  INITIAL_PMS_CREATE_MODAL_STATE,
  pmsCreateModalReducer,
} from './pms-create-modal-model';

export const CreateTaskListModal = ({
  isOpen,
  canCreate,
  onClose,
  teamId = null,
  folderId = null,
  onCreated,
}: {
  isOpen: boolean;
  canCreate: boolean;
  onClose: () => void;
  teamId?: string | null;
  folderId?: string | null;
  onCreated?: (taskList: PmsTaskList) => void;
}) => {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const nameInputId = useId();
  const descriptionInputId = useId();
  const [{ description, error, name, submitting }, dispatch] = useReducer(
    pmsCreateModalReducer,
    INITIAL_PMS_CREATE_MODAL_STATE,
  );

  const generation = useRef(0);
  useEffect(() => {
    dispatch({ type: 'reset' });
    return () => {
      generation.current += 1;
    };
  }, [token, teamId, folderId, isOpen, canCreate]);

  function handleClose() {
    generation.current += 1;
    dispatch({ type: 'reset' });
    onClose();
  }

  async function handleCreate() {
    if (
      !token ||
      !isOpen ||
      !canCreate ||
      submitting ||
      !canSubmitCreateName(name)
    )
      return;
    const operation = generation.current;
    dispatch({ type: 'submit' });
    try {
      const taskList = await createPmsTaskList(
        token,
        createTaskListPayload({ name, description, teamId, folderId }),
      );
      if (operation !== generation.current) return;
      onCreated?.(taskList);
      handleClose();
    } catch (err) {
      if (operation !== generation.current) return;
      dispatch({
        type: 'failed',
        message:
          err instanceof Error ? err.message : t('apps:pms.createListFailed'),
      });
    } finally {
      if (operation === generation.current) dispatch({ type: 'finished' });
    }
  }

  return (
    <FormDialog
      cancelLabel={t('common:actions.cancel')}
      closeLabel={t('common:actions.close')}
      open={isOpen && canCreate}
      onCancel={handleClose}
      onPrimary={() => void handleCreate()}
      title={t('apps:pms.createList')}
      maxWidth="max-w-lg"
      primaryDisabled={!canCreate || !canSubmitCreateName(name)}
      primaryLabel={t('apps:pms.create')}
      primaryPendingLabel={t('apps:pms.creating')}
      submitting={submitting}
    >
      <div className="space-y-5 text-app-ink">
        <div className="app-text-body text-app-ink/60">
          {t('apps:pms.createListDescription')}
        </div>

        {error && (
          <InlineNotice role="alert" tone="danger">
            {error}
          </InlineNotice>
        )}

        <FormFieldRow htmlFor={nameInputId} label={t('apps:pms.name')} required>
          <input
            id={nameInputId}
            type="text"
            placeholder={t('apps:pms.listNamePlaceholder')}
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

        <FormFieldRow
          htmlFor={descriptionInputId}
          label={t('apps:pms.description')}
          optionalLabel={t('apps:pms.optional')}
        >
          <textarea
            id={descriptionInputId}
            placeholder={t('apps:pms.listDescriptionPlaceholder')}
            value={description}
            onChange={(event) =>
              dispatch({
                type: 'description',
                value: event.target.value,
              })
            }
            rows={3}
            className={FORM_TEXTAREA_CONTROL_CLASS_NAME}
          />
        </FormFieldRow>
      </div>
    </FormDialog>
  );
};
