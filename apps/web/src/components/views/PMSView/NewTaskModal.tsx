import { useState } from 'react';
import {
  ChevronDown,
  Circle,
  FileText,
  Sparkles,
  User,
  Calendar,
  Flag,
  Tag,
  MoreHorizontal,
  Plus,
  LayoutTemplate,
  Paperclip,
  Bell,
} from 'lucide-react';
import { Dialog, Button, Badge, BlockEditor } from '@aidoo/ui';
import type { BlockContent } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import { useMediaUpload } from '@/src/domains/media/use-media-upload';
import { createProjectIssue, listTaskTemplates, type PmsProjectStatus, type PmsTaskTemplate } from '@/src/domains/pms/pms-api';
import { getStatusSlugs, getStatusLabel } from './pms-constants';

export const NewTaskModal = ({
  isOpen,
  onClose,
  projectId,
  onCreated,
  projectStatuses,
}: {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  onCreated?: () => void;
  projectStatuses?: PmsProjectStatus[];
}) => {
  const { token } = useAuth();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const [title, setTitle] = useState('');
  const defaultStatus = projectStatuses && projectStatuses.length > 0 ? projectStatuses[0].slug : 'backlog';
  const [status, setStatus] = useState(defaultStatus);
  const [priority, setPriority] = useState('medium');
  const [dueDate, setDueDate] = useState('');
  const [showDescription, setShowDescription] = useState(false);
  const [descriptionBlocks, setDescriptionBlocks] = useState<BlockContent | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [templates, setTemplates] = useState<PmsTaskTemplate[]>([]);
  const [templateMenuOpen, setTemplateMenuOpen] = useState(false);

  // Load templates when menu opens
  const openTemplateMenu = async () => {
    if (!token || !projectId) return;
    setTemplateMenuOpen(true);
    try {
      const res = await listTaskTemplates(token, projectId);
      setTemplates(res.items);
    } catch { /* ignore */ }
  };

  const applyTemplate = (t: PmsTaskTemplate) => {
    setTitle(t.name);
    setStatus(t.default_status);
    setPriority(t.default_priority);
    if (t.description) setShowDescription(true);
    setTemplateMenuOpen(false);
  };

  async function handleCreate() {
    if (!token || !title.trim() || !projectId) return;
    setSubmitting(true);
    try {
      await createProjectIssue(token, projectId, {
        title: title.trim(),
        description: '',
        description_blocks: descriptionBlocks as any ?? null,
        status,
        priority,
        assignee_id: null,
        milestone_id: null,
        due_date: dueDate || null,
      });
      onCreated?.();
      onClose();
    } catch {
      // TODO: toast error
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="New Task"
      maxWidth="max-w-3xl"
      actions={
        <div className="flex items-center justify-between w-full">
          <div className="relative">
            <Button variant="secondary" className="gap-2" onClick={openTemplateMenu}>
              <LayoutTemplate size={16} className="text-clickup-text/50" />
              Templates
            </Button>
            {templateMenuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setTemplateMenuOpen(false)} />
                <div className="absolute bottom-full left-0 mb-1 z-20 w-56 bg-clickup-bg border border-clickup-border rounded-lg shadow-xl py-1 max-h-48 overflow-y-auto">
                  {templates.length === 0 ? (
                    <p className="px-3 py-2 text-xs text-clickup-text/40">No templates yet</p>
                  ) : (
                    templates.map(t => (
                      <button
                        key={t.id}
                        onClick={() => applyTemplate(t)}
                        className="w-full text-left px-3 py-2 text-sm text-clickup-text hover:bg-clickup-hover transition-colors"
                      >
                        {t.name}
                      </button>
                    ))
                  )}
                </div>
              </>
            )}
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-4 text-clickup-text/50">
              <Paperclip size={20} className="cursor-pointer hover:text-clickup-text transition-colors" />
              <div className="flex items-center gap-1 cursor-pointer hover:text-clickup-text transition-colors">
                <Bell size={20} />
              </div>
            </div>
            <div className="flex items-center">
              <Button
                variant="primary"
                onClick={handleCreate}
                disabled={!title.trim() || submitting}
                className="rounded-r-none"
              >
                {submitting ? 'Creating...' : 'Create Task'}
              </Button>
              <Button variant="primary" size="icon" className="rounded-l-none border-l border-white/20">
                <ChevronDown size={20} />
              </Button>
            </div>
          </div>
        </div>
      }
    >
      <div className="space-y-6 text-clickup-text">
        {/* Task Name Input */}
        <input
          type="text"
          placeholder="Task Name"
          value={title}
          onChange={e => setTitle(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && title.trim() && !submitting) handleCreate(); }}
          className="w-full bg-transparent text-xl font-medium text-clickup-text placeholder:text-clickup-text/40 focus:outline-none border border-clickup-border rounded-lg px-4 py-3 focus:border-clickup-purple transition-all"
          autoFocus
        />

        {/* Description */}
        <div className="space-y-4">
          {showDescription ? (
            <div className="rounded-lg border border-clickup-border bg-clickup-sidebar overflow-hidden">
              <BlockEditor
                initialContent={descriptionBlocks}
                onChange={setDescriptionBlocks}
                placeholder="Add a description..."
                className="[&_.bn-editor]:min-h-[80px] [&_.bn-editor]:px-2"
                uploadFile={uploadFile}
                resolveFileUrl={resolveFileUrl}
              />
            </div>
          ) : (
            <button
              className="flex items-center gap-2 text-clickup-text/50 hover:text-clickup-text transition-colors text-sm"
              onClick={() => setShowDescription(true)}
            >
              <FileText size={18} />
              <span>Add description</span>
            </button>
          )}
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            className="bg-clickup-sidebar border border-clickup-border rounded-md px-2 py-1 text-xs text-clickup-text focus:outline-none"
          >
            {getStatusSlugs(projectStatuses).map(s => (
              <option key={s} value={s}>{getStatusLabel(s, projectStatuses)}</option>
            ))}
          </select>

          <select
            value={priority}
            onChange={e => setPriority(e.target.value)}
            className="bg-clickup-sidebar border border-clickup-border rounded-md px-2 py-1 text-xs text-clickup-text focus:outline-none"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>

          <input
            type="date"
            value={dueDate}
            onChange={e => setDueDate(e.target.value)}
            className="bg-clickup-sidebar border border-clickup-border rounded-md px-2 py-1 text-xs text-clickup-text focus:outline-none"
          />
        </div>
      </div>
    </Dialog>
  );
};
