import { useState, useEffect } from 'react';
import { FolderKanban } from 'lucide-react';
import { Dialog, Button } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { createPmsProject, type PmsProject } from '@/src/domains/pms/pms-api';

export const CreateProjectModal = ({
  isOpen,
  onClose,
  teamId = null,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  teamId?: string | null;
  onCreated?: (project: PmsProject) => void;
}) => {
  const { token } = useAuth();
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Reset form when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setName('');
      setKey('');
      setDescription('');
      setError('');
      setSubmitting(false);
    }
  }, [isOpen]);

  const autoKey = (value: string) => {
    setName(value);
    if (!key || key === nameToKey(name)) {
      setKey(nameToKey(value));
    }
  };

  async function handleCreate() {
    if (!token || !name.trim() || !key.trim()) return;
    setSubmitting(true);
    setError('');
    try {
      const project = await createPmsProject(token, {
        key: key.trim().toUpperCase(),
        name: name.trim(),
        description: description.trim(),
        team_id: teamId,
      });
      onCreated?.(project);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '프로젝트 생성에 실패했습니다.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="New List"
      maxWidth="max-w-lg"
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || !key.trim() || submitting}
          >
            {submitting ? 'Creating...' : 'Create List'}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-clickup-text">
        <div className="flex items-center gap-3 p-4 rounded-lg bg-clickup-sidebar border border-clickup-border">
          <div className="w-10 h-10 bg-blue-500/20 rounded-lg flex items-center justify-center">
            <FolderKanban size={20} className="text-blue-400" />
          </div>
          <div className="text-sm text-clickup-text/60">
            리스트를 생성하면 이슈, 마일스톤, 라벨 등을 관리할 수 있습니다.
          </div>
        </div>

        {error && (
          <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="text-xs font-medium text-clickup-text/70">List Name</label>
          <input
            type="text"
            placeholder="e.g. Website Redesign"
            value={name}
            onChange={e => autoKey(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && name.trim() && key.trim() && !submitting) handleCreate(); }}
            className="w-full bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-2 text-sm text-clickup-text placeholder:text-clickup-text/30 focus:outline-none focus:border-clickup-purple transition-all"
            autoFocus
          />
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-clickup-text/70">List Key</label>
          <input
            type="text"
            placeholder="e.g. WEB"
            value={key}
            onChange={e => setKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''))}
            maxLength={24}
            className="w-full bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-2 text-sm text-clickup-text placeholder:text-clickup-text/30 focus:outline-none focus:border-clickup-purple transition-all font-mono"
          />
          <p className="text-[10px] text-clickup-text/40">이슈 번호 접두사로 사용됩니다 (예: {key || 'WEB'}-1)</p>
        </div>

        <div className="space-y-1">
          <label className="text-xs font-medium text-clickup-text/70">Description <span className="text-clickup-text/30">(optional)</span></label>
          <textarea
            placeholder="리스트에 대한 간단한 설명"
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={3}
            className="w-full bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-2 text-sm text-clickup-text placeholder:text-clickup-text/30 focus:outline-none focus:border-clickup-purple transition-all resize-none"
          />
        </div>
      </div>
    </Dialog>
  );
};

function nameToKey(name: string): string {
  return name
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9\s]/g, '')
    .split(/\s+/)
    .map(w => w[0] ?? '')
    .join('')
    .slice(0, 6);
}
