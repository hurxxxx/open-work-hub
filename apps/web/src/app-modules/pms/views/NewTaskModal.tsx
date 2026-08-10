import { useEffect, useReducer, useRef, useState } from 'react';
import {
  ChevronDown,
  FileText,
  LayoutTemplate,
  Paperclip,
  Bell,
  Search,
  X,
} from 'lucide-react';
import { Dialog, Button, BlockEditor, InlineNotice } from '@open-alm/ui';
import { useTranslation } from 'react-i18next';
import { DateInput } from '@/src/components/date/DateInput';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { useMediaUpload } from '@/src/platform/media/use-media-upload';
import {
  createTaskListTask,
  listSpaceMembers,
  listTaskTemplates,
  type PmsTask,
  type PmsTaskListStatus,
  type PmsTaskTemplate,
} from '../api/pms-api';
import {
  buildNewTaskCreatePayload,
  createInitialNewTaskState,
  newTaskReducer,
} from './new-task-modal-model';
import { TaskPickerModal, type TaskPickerModalCopy } from './TaskPickerModal';

const PARENT_TASK_PICKER_COPY: TaskPickerModalCopy = {
  titleKey: 'pms.parentTaskPicker.title',
  descriptionKey: 'pms.parentTaskPicker.description',
  workspaceLabelKey: 'pms.taskPicker.pmsWorkspace',
  noAccessActionKey: 'pms.parentTaskPicker.action',
  loadListsErrorKey: 'pms.taskPicker.errors.loadListsFailed',
  loadTasksErrorKey: 'pms.parentTaskPicker.errors.loadTasksFailed',
  attachErrorKey: 'pms.parentTaskPicker.errors.selectFailed',
  taskListLabelKey: 'pms.taskPicker.taskListLabel',
  noTaskListsKey: 'pms.taskPicker.noTaskLists',
  searchPlaceholderKey: 'pms.parentTaskPicker.searchPlaceholder',
  emptyKey: 'pms.parentTaskPicker.empty',
};

export const NewTaskModal = ({
  canCreate = true,
  contentClassName,
  initialTitle,
  isOpen,
  onClose,
  onCreated,
  onTaskListIdChange,
  onWorkspaceSlugChange,
  overlayClassName,
  parentPickerContentClassName,
  parentPickerOverlayClassName,
  taskListSpaceId,
  taskListId,
  taskListLoading = false,
  taskListOptions,
  taskListStatuses,
  workspaceOptions,
  workspaceSlug,
}: {
  canCreate?: boolean;
  contentClassName?: string;
  initialTitle?: string | null;
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (task: PmsTask) => void;
  onTaskListIdChange?: (taskListId: string) => void;
  onWorkspaceSlugChange?: (workspaceSlug: string) => void;
  overlayClassName?: string;
  parentPickerContentClassName?: string;
  parentPickerOverlayClassName?: string;
  taskListSpaceId?: string | null;
  taskListId: string;
  taskListLoading?: boolean;
  taskListOptions?: readonly { id: string; label: string }[];
  taskListStatuses?: PmsTaskListStatus[];
  workspaceOptions?: readonly { label: string; slug: string }[];
  workspaceSlug?: string | null;
}) => {
  const { t } = useTranslation('apps');
  const { token, user } = useAuth();
  const { uploadFile, resolveFileUrl } = useMediaUpload();
  const closeLabel = t('common:actions.close');
  const explicitDismissRequestedRef = useRef(false);
  const [newTaskState, dispatch] = useReducer(
    newTaskReducer,
    { initialTitle, taskListStatuses },
    ({ initialTitle: title, taskListStatuses: statuses }) =>
      createInitialNewTaskState(statuses, title ?? ''),
  );
  const [canAssignToMe, setCanAssignToMe] = useState(false);
  const [parentPickerOpen, setParentPickerOpen] = useState(false);
  const [selectedParentTask, setSelectedParentTask] = useState<PmsTask | null>(
    null,
  );
  const {
    descriptionBlocks,
    assignToMe,
    dueDate,
    error,
    priority,
    showDescription,
    startDate,
    submitting,
    templateMenuOpen,
    templates,
    title,
  } = newTaskState;

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    let resetExplicitDismissTimeout: number | undefined;
    const markExplicitDismiss = (event: MouseEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest('button')?.getAttribute('aria-label') === closeLabel
      ) {
        explicitDismissRequestedRef.current = true;
        window.clearTimeout(resetExplicitDismissTimeout);
        resetExplicitDismissTimeout = window.setTimeout(() => {
          explicitDismissRequestedRef.current = false;
        }, 0);
      }
    };
    const stopEscapePropagation = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
      }
    };

    document.addEventListener('click', markExplicitDismiss, true);
    document.addEventListener('keydown', stopEscapePropagation);
    return () => {
      document.removeEventListener('click', markExplicitDismiss, true);
      document.removeEventListener('keydown', stopEscapePropagation);
      window.clearTimeout(resetExplicitDismissTimeout);
      explicitDismissRequestedRef.current = false;
    };
  }, [closeLabel, isOpen]);

  useEffect(() => {
    setParentPickerOpen(false);
    setSelectedParentTask(null);
    dispatch({ type: 'parent-id', value: null });
  }, [taskListId]);

  useEffect(() => {
    let cancelled = false;
    setCanAssignToMe(false);
    if (!token || !taskListSpaceId || !user?.id) {
      dispatch({ type: 'assign-to-me', value: false });
      return () => {
        cancelled = true;
      };
    }

    listSpaceMembers(token, taskListSpaceId, workspaceSlug)
      .then((response) => {
        if (cancelled) {
          return;
        }
        const isMember = response.items.some(
          (member) => member.user_id === user.id,
        );
        setCanAssignToMe(isMember);
        if (!isMember) {
          dispatch({ type: 'assign-to-me', value: false });
        }
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setCanAssignToMe(false);
        dispatch({ type: 'assign-to-me', value: false });
      });

    return () => {
      cancelled = true;
    };
  }, [taskListSpaceId, token, user?.id, workspaceSlug]);

  // Load templates when menu opens
  const openTemplateMenu = async () => {
    if (!token || !taskListId) return;
    dispatch({ type: 'open-template-menu' });
    try {
      const res = await listTaskTemplates(token, taskListId, workspaceSlug);
      dispatch({
        type: 'templates-loaded',
        templates: res.items,
      });
    } catch {
      /* ignore */
    }
  };

  const applyTemplate = (template: PmsTaskTemplate) => {
    dispatch({
      type: 'apply-template',
      taskListStatuses,
      template,
    });
  };

  const handleStartDateChange = (value: string) => {
    dispatch({
      type: 'start-date',
      value,
    });
  };

  const handleDueDateChange = (value: string) => {
    dispatch({
      type: 'due-date',
      value,
    });
  };

  async function handleCreate() {
    if (!token || !title.trim() || !taskListId || !canCreate) return;
    dispatch({ type: 'submit' });
    try {
      const createdTask = await createTaskListTask(
        token,
        taskListId,
        buildNewTaskCreatePayload(newTaskState, taskListStatuses, {
          assignToUserId: user?.id ?? null,
        }),
        workspaceSlug,
      );
      onCreated?.(createdTask);
      onClose();
    } catch {
      dispatch({
        type: 'failed',
        message: t('pms.errors.createTaskFailed'),
      });
    } finally {
      dispatch({ type: 'finished' });
    }
  }

  const clearParentTask = () => {
    setSelectedParentTask(null);
    dispatch({ type: 'parent-id', value: null });
  };

  return (
    <>
      <Dialog
        closeLabel={closeLabel}
        contentClassName={contentClassName}
        dismissOnInteractOutside={false}
        open={isOpen}
        onOpenChange={(open) => {
          if (!open && explicitDismissRequestedRef.current) onClose();
        }}
        overlayClassName={overlayClassName}
        title={t('pms.newTask')}
        maxWidth="max-w-3xl"
        actions={
          <div className="flex items-center justify-between w-full">
            <div className="relative">
              <Button
                variant="secondary"
                className="gap-2"
                onClick={openTemplateMenu}
              >
                <LayoutTemplate size={16} className="text-app-ink/50" />
                {t('pms.templates')}
              </Button>
              {templateMenuOpen && (
                <>
                  <button
                    type="button"
                    aria-label={t('common:actions.close')}
                    className="fixed inset-0 z-10 cursor-default"
                    onClick={() => dispatch({ type: 'close-template-menu' })}
                    tabIndex={-1}
                  />
                  <div className="absolute bottom-full left-0 mb-1 z-20 w-56 bg-app-bg border border-app-border rounded-lg shadow-xl py-1 max-h-48 overflow-y-auto">
                    {templates.length === 0 ? (
                      <p className="app-text-caption px-3 py-2 text-app-ink/40">
                        {t('pms.noTemplates')}
                      </p>
                    ) : (
                      templates.map((t) => (
                        <button
                          key={t.id}
                          type="button"
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
                <Paperclip
                  size={20}
                  className="cursor-pointer hover:text-app-ink transition-colors"
                />
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
                <Button
                  variant="primary"
                  size="icon"
                  className="rounded-l-none border-l border-white/20"
                  aria-label={t('pms.createTask')}
                >
                  <ChevronDown size={20} />
                </Button>
              </div>
            </div>
          </div>
        }
      >
        <div className="space-y-6 text-app-ink">
          {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

          {workspaceOptions?.length ? (
            <label className="app-text-caption flex flex-col gap-1 text-app-ink/60">
              <span>{t('common:labels.workspace')}</span>
              <select
                className="app-field-input-sm"
                disabled={submitting}
                value={workspaceSlug ?? ''}
                onChange={(event) =>
                  onWorkspaceSlugChange?.(event.target.value)
                }
              >
                {workspaceOptions.map((option) => (
                  <option key={option.slug} value={option.slug}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {taskListOptions !== undefined ? (
            <div className="app-text-caption flex flex-col gap-1 text-app-ink/60">
              <span>{t('pms.floating.taskList')}</span>
              {taskListLoading ? (
                <InlineNotice tone="info">
                  {t('common:feedback.loading')}
                </InlineNotice>
              ) : taskListOptions.length > 0 ? (
                <select
                  aria-label={t('pms.floating.taskList')}
                  className="app-field-input-sm"
                  disabled={submitting || !canCreate}
                  value={taskListId}
                  onChange={(event) => onTaskListIdChange?.(event.target.value)}
                >
                  {taskListOptions.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : (
                <InlineNotice tone="warning">
                  {t('pms.floating.noEditableLists')}
                </InlineNotice>
              )}
            </div>
          ) : null}

          <div className="app-text-caption flex flex-col gap-1 text-app-ink/60">
            <span>{t('pms.parentTask')}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="app-field-input-sm flex min-w-0 flex-1 items-center gap-2 bg-app-surface-sidebar py-1 text-left"
                disabled={!canCreate || submitting || !taskListId}
                onClick={() => setParentPickerOpen(true)}
              >
                <Search size={14} className="shrink-0 text-app-ink/45" />
                {selectedParentTask ? (
                  <span className="min-w-0 truncate text-app-ink">
                    {selectedParentTask.reference} · {selectedParentTask.title}
                  </span>
                ) : (
                  <span className="text-app-ink/45">
                    {t('pms.noParentTask')}
                  </span>
                )}
              </button>
              {selectedParentTask ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  aria-label={t('pms.clearParentTask')}
                  disabled={!canCreate || submitting}
                  onClick={clearParentTask}
                >
                  <X size={16} />
                </Button>
              ) : null}
            </div>
          </div>

          {/* Task Name Input */}
          <input
            type="text"
            aria-label={t('pms.taskName')}
            placeholder={t('pms.taskName')}
            value={title}
            onChange={(event) =>
              dispatch({
                type: 'title',
                value: event.target.value,
              })
            }
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                !event.nativeEvent.isComposing &&
                title.trim() &&
                !submitting &&
                canCreate
              ) {
                void handleCreate();
              }
            }}
            className="app-text-title-md w-full rounded-lg border border-app-border bg-transparent px-4 py-3 font-medium text-app-ink placeholder:text-app-ink/40 transition-all focus:border-app-accent focus:outline-none"
            disabled={!canCreate}
          />

          {/* Description */}
          <div className="space-y-4">
            {showDescription ? (
              <div className="rounded-lg border border-app-border bg-app-surface-sidebar overflow-hidden">
                <BlockEditor
                  initialContent={descriptionBlocks}
                  onChange={(value) =>
                    dispatch({
                      type: 'description-blocks',
                      value,
                    })
                  }
                  placeholder={t('pms.descriptionPlaceholder')}
                  className="[&_.bn-editor]:min-h-[80px] [&_.bn-editor]:px-2"
                  uploadFile={uploadFile}
                  resolveFileUrl={resolveFileUrl}
                />
              </div>
            ) : (
              <button
                type="button"
                className="app-text-body flex items-center gap-2 text-app-ink/50 transition-colors hover:text-app-ink"
                onClick={() => dispatch({ type: 'show-description' })}
                disabled={!canCreate}
              >
                <FileText size={18} />
                <span>{t('pms.addDescription')}</span>
              </button>
            )}
          </div>

          {/* Quick Actions */}
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="app-text-caption flex flex-col gap-1 text-app-ink/60">
              <span>{t('pms.filter.startDateLabel')}</span>
              <DateInput
                value={startDate}
                onValueChange={handleStartDateChange}
                className="app-field-input-sm bg-app-surface-sidebar py-1"
                disabled={!canCreate}
              />
            </label>

            <label className="app-text-caption flex flex-col gap-1 text-app-ink/60">
              <span>{t('pms.filter.dueDateLabel')}</span>
              <DateInput
                value={dueDate}
                onValueChange={handleDueDateChange}
                className="app-field-input-sm bg-app-surface-sidebar py-1"
                disabled={!canCreate}
              />
            </label>

            <label className="app-text-caption flex flex-col gap-1 text-app-ink/60">
              <span>{t('pms.filter.priorityLabel')}</span>
              <select
                value={priority}
                onChange={(event) =>
                  dispatch({
                    type: 'priority',
                    value: event.target.value,
                  })
                }
                className="app-field-input-sm"
                disabled={!canCreate}
              >
                <option value="low">{t('pms.priorityLow')}</option>
                <option value="medium">{t('pms.priorityMedium')}</option>
                <option value="high">{t('pms.priorityHigh')}</option>
                <option value="critical">{t('pms.priorityCritical')}</option>
              </select>
            </label>
          </div>

          <label className="app-text-body flex items-center gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink">
            <input
              type="checkbox"
              className="size-4 rounded border-app-border accent-app-accent"
              checked={assignToMe}
              disabled={!canCreate || submitting || !canAssignToMe}
              onChange={(event) =>
                dispatch({
                  type: 'assign-to-me',
                  value: event.target.checked,
                })
              }
            />
            <span>{t('pms.assignToMe')}</span>
            {!canAssignToMe ? (
              <span className="app-text-caption text-app-ink/45">
                {t('pms.assignToMeUnavailable')}
              </span>
            ) : null}
          </label>
        </div>
      </Dialog>
      {parentPickerOpen ? (
        <TaskPickerModal
          contentClassName={parentPickerContentClassName}
          copy={PARENT_TASK_PICKER_COPY}
          fixedTaskListId={taskListId}
          isOpen={parentPickerOpen}
          layer="elevated"
          onClose={() => setParentPickerOpen(false)}
          onPick={(task) => {
            setSelectedParentTask(task);
            dispatch({ type: 'parent-id', value: task.id });
          }}
          overlayClassName={parentPickerOverlayClassName}
          workspaceSlug={workspaceSlug}
        />
      ) : null}
    </>
  );
};
