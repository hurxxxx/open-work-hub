import { useState, useEffect } from 'react';
import { Layout } from 'lucide-react';
import { Dialog, Button } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { hasAppAccess } from '@/src/domains/auth/auth-api';
import { createSpace, type PmsSpace } from '@/src/domains/pms/pms-api';

export const CreateSpaceModal = ({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (space: PmsSpace) => void;
}) => {
  const { token, user } = useAuth();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const canCreateSpace = hasAppAccess(user, 'pms');

  // Reset form when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setName('');
      setDescription('');
      setError('');
      setSubmitting(false);
    }
  }, [isOpen]);

  async function handleCreate() {
    if (!token || !name.trim() || !canCreateSpace) return;
    setSubmitting(true);
    setError('');
    try {
      const space = await createSpace(token, {
        name: name.trim(),
        description: description.trim(),
      });
      onCreated?.(space);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '스페이스 생성에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="New Space"
      maxWidth="max-w-lg"
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || !canCreateSpace || submitting}
          >
            {submitting ? 'Creating...' : 'Create Space'}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-clickup-text">
        <div className="flex items-center gap-3 p-4 rounded-lg bg-clickup-sidebar border border-clickup-border">
          <div className="w-10 h-10 bg-clickup-purple/20 rounded-lg flex items-center justify-center">
            <Layout size={20} className="text-clickup-purple" />
          </div>
          <div className="app-text-body text-clickup-text/60">
            스페이스는 팀 단위의 작업 공간입니다. 리스트와 멤버를 묶어 관리할 수 있습니다.
          </div>
        </div>

        {!canCreateSpace && (
          <div className="app-text-body rounded-md border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-amber-400">
            PMS 앱 접근 권한이 없어 스페이스를 생성할 수 없습니다.
          </div>
        )}

        {error && (
          <div className="app-text-body rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2 text-red-400">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="app-text-control-sm text-clickup-text/70">Space Name</label>
          <input
            type="text"
            placeholder="e.g. Engineering"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && name.trim() && !submitting) handleCreate(); }}
            className="app-text-body w-full rounded-md border border-clickup-border bg-clickup-sidebar px-3 py-2 text-clickup-text placeholder:text-clickup-text/30 transition-all focus:border-clickup-purple focus:outline-none"
            autoFocus
          />
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-clickup-text/70">Description <span className="text-clickup-text/30">(optional)</span></label>
          <textarea
            placeholder="스페이스에 대한 간단한 설명"
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            className="app-text-body w-full resize-none rounded-md border border-clickup-border bg-clickup-sidebar px-3 py-2 text-clickup-text placeholder:text-clickup-text/30 transition-all focus:border-clickup-purple focus:outline-none"
          />
        </div>
      </div>
    </Dialog>
  );
};
