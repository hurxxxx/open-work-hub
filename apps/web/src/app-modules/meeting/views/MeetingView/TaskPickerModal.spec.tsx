import { isValidElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TaskPickerModal } from './TaskPickerModal';

describe('Meeting TaskPickerModal', () => {
  it('adapts the shared PMS task picker with meeting copy', () => {
    const excludeTaskIds = ['task-1'];
    const element = TaskPickerModal({
      isOpen: true,
      onClose: vi.fn(),
      onPick: vi.fn(),
      excludeTaskIds,
    });

    expect(isValidElement(element)).toBe(true);
    if (!isValidElement(element)) {
      throw new Error('Expected TaskPickerModal to return a React element');
    }

    const props = element.props as {
      copy: Record<string, string>;
      excludeTaskIds: string[];
      isOpen: boolean;
    };

    expect(props.isOpen).toBe(true);
    expect(props).not.toHaveProperty('workspaceSlug');
    expect(props.excludeTaskIds).toBe(excludeTaskIds);
    expect(props.copy).toEqual({
      titleKey: 'meeting.taskPicker.title',
      descriptionKey: 'meeting.taskPicker.description',
      appLabelKey: 'meeting.taskPicker.pmsWorkspace',
      noAccessActionKey: 'meeting.taskPicker.attachAction',
      loadListsErrorKey: 'meeting.taskPicker.listLoadFailed',
      loadTasksErrorKey: 'meeting.taskPicker.issueLoadFailed',
      attachErrorKey: 'meeting.taskPicker.attachFailed',
      taskListLabelKey: 'meeting.taskPicker.list',
      noTaskListsKey: 'meeting.taskPicker.noLists',
      searchPlaceholderKey: 'meeting.taskPicker.searchPlaceholder',
      emptyKey: 'meeting.taskPicker.empty',
    });
  });
});
