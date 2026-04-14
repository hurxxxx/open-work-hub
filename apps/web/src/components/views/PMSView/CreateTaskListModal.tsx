import { useState, useEffect } from 'react';
import { Dialog, Button } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { createPmsTaskList, type PmsTaskList } from '@/src/domains/pms/pms-api';

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
      setError(err instanceof Error ? err.message : '리스트 생성에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="Create List"
      maxWidth="max-w-lg"
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || submitting}
          >
            {submitting ? 'Creating...' : 'Create'}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        <div className="app-text-body text-app-ink/60">
          All Lists are located within a Space. Lists can house any type of task.
        </div>

        {error && (
          <div className="app-text-body rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-red-400">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            Name <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            placeholder="e.g. Sprint Backlog, Design Ops, Q2 Campaign"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && name.trim() && !submitting) handleCreate(); }}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none"
            autoFocus
          />
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">Description <span className="text-app-ink/30">(optional)</span></label>
          <textarea
            placeholder="리스트에 대한 간단한 설명"
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
