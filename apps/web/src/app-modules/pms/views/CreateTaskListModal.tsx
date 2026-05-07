import { useState, useEffect } from 'react';
import { Dialog, Button } from '@ai-do/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { createPmsTaskList, type PmsTaskList } from '../api/pms-api';

export const CreateTaskListModal = ({
  isOpen,
  onClose,
  teamId = null,
  folderId = null,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  teamId?: string | null;
  folderId?: string | null;
  onCreated?: (taskList: PmsTaskList) => void;
}) => {
  const { t } = useTranslation(['apps', 'common']);
  const { token } = useAuth();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setName('');
      setDescription('');
      setError('');
      setSubmitting(false);
    }
  }, [isOpen]);

  async function handleCreate() {
    if (!token || !name.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const taskList = await createPmsTaskList(token, {
        name: name.trim(),
        description: description.trim(),
        team_id: teamId,
        folder_id: folderId,
      });
      onCreated?.(taskList);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:pms.createListFailed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
        closeLabel={t('common:actions.close')}
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title={t('apps:pms.createList')}
      maxWidth="max-w-lg"
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>{t('common:actions.cancel')}</Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || submitting}
          >
            {submitting ? t('apps:pms.creating') : t('apps:pms.create')}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        <div className="app-text-body text-app-ink/60">
          {t('apps:pms.createListDescription')}
        </div>

        {error && (
          <div className="app-text-body rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-red-400">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('apps:pms.name')} <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            placeholder={t('apps:pms.listNamePlaceholder')}
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && name.trim() && !submitting) handleCreate(); }}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none"
            autoFocus
          />
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('apps:pms.description')} <span className="text-app-ink/30">({t('apps:pms.optional')})</span>
          </label>
          <textarea
            placeholder={t('apps:pms.listDescriptionPlaceholder')}
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            className="app-text-body w-full resize-none rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none"
          />
        </div>
      </div>
    </Dialog>
  );
};
