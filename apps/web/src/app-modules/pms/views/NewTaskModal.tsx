import { useState } from 'react';
import {
  ChevronDown,
  FileText,
  LayoutTemplate,
  Paperclip,
  Bell,
} from 'lucide-react';
import { Dialog, Button, BlockEditor } from '@aidoo/ui';
import type { BlockContent } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import { createTaskListIssue, listTaskTemplates, type PmsTaskListStatus, type PmsTaskTemplate } from '../api/pms-api';
import { getStatusSlugs, getStatusLabel } from './pms-constants';

export const NewTaskModal = ({
  isOpen,
  onClose,
  taskListId,
  onCreated,
  taskListStatuses,
  canCreate = true,
}: {
  isOpen: boolean;
  onClose: () => void;
  taskListId: string;
  onCreated?: () => void;
  taskListStatuses?: PmsTaskListStatus[];
  canCreate?: boolean;
}) => {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const [title, setTitle] = useState('');
  const defaultStatus = taskListStatuses && taskListStatuses.length > 0 ? taskListStatuses[0].slug : 'backlog';
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
    if (!token || !taskListId) return;
    setTemplateMenuOpen(true);
    try {
      const res = await listTaskTemplates(token, taskListId);
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
    if (!token || !title.trim() || !taskListId || !canCreate) return;
    setSubmitting(true);
    try {
      await createTaskListIssue(token, taskListId, {
        title: title.trim(),
        description: '',
        description_blocks: descriptionBlocks ?? null,
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
      title={t('pms.newTask')}
      maxWidth="max-w-3xl"
      actions={
        <div className="flex items-center justify-between w-full">
          <div className="relative">
            <Button variant="secondary" className="gap-2" onClick={openTemplateMenu}>
              <LayoutTemplate size={16} className="text-app-ink/50" />
              {t('pms.templates')}
            </Button>
            {templateMenuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setTemplateMenuOpen(false)} />
                <div className="absolute bottom-full left-0 mb-1 z-20 w-56 bg-app-bg border border-app-border rounded-lg shadow-xl py-1 max-h-48 overflow-y-auto">
                  {templates.length === 0 ? (
                    <p className="app-text-caption px-3 py-2 text-app-ink/40">{t('pms.noTemplates')}</p>
                  ) : (
                    templates.map(t => (
                      <button
                        key={t.id}
                        onClick={() => applyTemplate(t)}
                        className="app-text-body w-full px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
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
            <div className="flex items-center gap-4 text-app-ink/50">
              <Paperclip size={20} className="cursor-pointer hover:text-app-ink transition-colors" />
              <div className="flex items-center gap-1 cursor-pointer hover:text-app-ink transition-colors">
                <Bell size={20} />
              </div>
            </div>
            <div className="flex items-center">
              <Button
                variant="primary"
                onClick={handleCreate}
                disabled={!title.trim() || submitting || !canCreate}
                className="rounded-r-none"
              >
                {submitting ? t('pms.creating') : t('pms.createTask')}
              </Button>
              <Button variant="primary" size="icon" className="rounded-l-none border-l border-white/20">
                <ChevronDown size={20} />
              </Button>
            </div>
          </div>
        </div>
      }
    >
      <div className="space-y-6 text-app-ink">
        {/* Task Name Input */}
        <input
          type="text"
          placeholder={t('pms.taskName')}
          value={title}
          onChange={e => setTitle(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing && title.trim() && !submitting && canCreate) handleCreate(); }}
          className="app-text-title-md w-full rounded-lg border border-app-border bg-transparent px-4 py-3 font-medium text-app-ink placeholder:text-app-ink/40 transition-all focus:border-app-accent focus:outline-none"
          autoFocus
          disabled={!canCreate}
        />

        {/* Description */}
        <div className="space-y-4">
          {showDescription ? (
            <div className="rounded-lg border border-app-border bg-app-surface-sidebar overflow-hidden">
              <BlockEditor
                initialContent={descriptionBlocks}
                onChange={setDescriptionBlocks}
                placeholder={t('pms.descriptionPlaceholder')}
                className="[&_.bn-editor]:min-h-[80px] [&_.bn-editor]:px-2"
                uploadFile={uploadFile}
                resolveFileUrl={resolveFileUrl}
              />
            </div>
          ) : (
            <button
              className="app-text-body flex items-center gap-2 text-app-ink/50 transition-colors hover:text-app-ink"
              onClick={() => setShowDescription(true)}
              disabled={!canCreate}
            >
              <FileText size={18} />
              <span>{t('pms.addDescription')}</span>
            </button>
          )}
        </div>

        {/* Quick Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            className="app-text-body-sm rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink focus:outline-none"
            disabled={!canCreate}
          >
            {getStatusSlugs(taskListStatuses).map(s => (
              <option key={s} value={s}>{getStatusLabel(s, taskListStatuses)}</option>
            ))}
          </select>

          <select
            value={priority}
            onChange={e => setPriority(e.target.value)}
            className="app-text-body-sm rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink focus:outline-none"
            disabled={!canCreate}
          >
            <option value="low">{t('pms.priorityLow')}</option>
            <option value="medium">{t('pms.priorityMedium')}</option>
            <option value="high">{t('pms.priorityHigh')}</option>
            <option value="critical">{t('pms.priorityCritical')}</option>
          </select>

          <input
            type="date"
            value={dueDate}
            onChange={e => setDueDate(e.target.value)}
            className="app-text-body-sm rounded-md border border-app-border bg-app-surface-sidebar px-2 py-1 text-app-ink focus:outline-none"
            disabled={!canCreate}
          />
        </div>
      </div>
    </Dialog>
  );
};
