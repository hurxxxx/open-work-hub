import {
  TaskPickerModal as PmsTaskPickerModal,
  type TaskPickerModalProps as PmsTaskPickerModalProps,
  type TaskPickerModalCopy,
} from '@/src/app-modules/pms/public-api';

export type TaskPickerModalProps = Omit<PmsTaskPickerModalProps, 'copy'>;

const MEETING_TASK_PICKER_COPY: TaskPickerModalCopy = {
  titleKey: 'meeting.taskPicker.title',
  descriptionKey: 'meeting.taskPicker.description',
  appLabelKey: 'meeting.taskPicker.pmsApp',
  noAccessActionKey: 'meeting.taskPicker.attachAction',
  loadListsErrorKey: 'meeting.taskPicker.listLoadFailed',
  loadTasksErrorKey: 'meeting.taskPicker.issueLoadFailed',
  attachErrorKey: 'meeting.taskPicker.attachFailed',
  taskListLabelKey: 'meeting.taskPicker.list',
  noTaskListsKey: 'meeting.taskPicker.noLists',
  searchPlaceholderKey: 'meeting.taskPicker.searchPlaceholder',
  emptyKey: 'meeting.taskPicker.empty',
};

export function TaskPickerModal(props: TaskPickerModalProps) {
  return <PmsTaskPickerModal {...props} copy={MEETING_TASK_PICKER_COPY} />;
}

export default TaskPickerModal;
