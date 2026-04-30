import { useState, useEffect } from 'react';
import { FolderOpen } from 'lucide-react';
import { Dialog, Button } from '@aidoo/ui';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { createFolder, type PmsFolder } from '../api/pms-api';

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
  const { token } = useAuth();
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      setName('');
      setError('');
      setSubmitting(false);
    }
  }, [isOpen]);

  async function handleCreate() {
    if (!token || !name.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const folder = await createFolder(token, { name: name.trim(), team_id: teamId });
      onCreated?.(folder);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '폴더 생성에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="New Folder"
      maxWidth="max-w-lg"
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || submitting}
          >
            {submitting ? 'Creating...' : 'Create Folder'}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        <div className="flex items-center gap-3 p-4 rounded-lg bg-app-surface-sidebar border border-app-border">
          <div className="w-10 h-10 bg-amber-500/20 rounded-lg flex items-center justify-center">
            <FolderOpen size={20} className="text-amber-400" />
          </div>
          <div className="app-text-body text-app-ink/60">
            폴더를 생성하면 리스트와 문서를 그룹으로 묶어 관리할 수 있습니다.
          </div>
        </div>

        {error && (
          <div className="app-text-body rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-red-400">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">Folder Name</label>
          <input
            type="text"
            placeholder="e.g. Sprint 1"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && name.trim() && !submitting) handleCreate(); }}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none"
            autoFocus
          />
        </div>
      </div>
    </Dialog>
  );
};
