import {
  TaskPickerModal as PmsTaskPickerModal,
  type TaskPickerModalCopy,
  type TaskPickerModalProps as PmsTaskPickerModalProps,
} from '@/src/app-modules/pms/public-api';

export type TaskPickerModalProps = Omit<PmsTaskPickerModalProps, 'copy'>;

const RECORDING_TASK_PICKER_COPY: TaskPickerModalCopy = {
  titleKey: 'recording.detail.taskPicker.title',
  descriptionKey: 'recording.detail.taskPicker.description',
  workspaceLabelKey: 'recording.title',
  noAccessActionKey: 'recording.detail.addTask',
  loadListsErrorKey: 'recording.errors.attachFailed',
  loadTasksErrorKey: 'recording.errors.attachFailed',
  attachErrorKey: 'recording.errors.attachFailed',
  taskListLabelKey: 'recording.detail.taskPicker.taskListLabel',
  noTaskListsKey: 'recording.detail.taskPicker.noTaskLists',
  searchPlaceholderKey: 'recording.detail.taskPicker.searchPlaceholder',
  emptyKey: 'common:empty.noResults',
};

export function TaskPickerModal(props: TaskPickerModalProps) {
  return <PmsTaskPickerModal {...props} copy={RECORDING_TASK_PICKER_COPY} />;
}

export default TaskPickerModal;
