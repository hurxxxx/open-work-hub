import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { NewTaskModal } from './NewTaskModal';

const taskPickerModalSpy = vi.hoisted(() => vi.fn());
const dialogSpy = vi.hoisted(() => vi.fn());

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@open-work-hub/ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@open-work-hub/ui')>();
  return {
    ...actual,
    BlockEditor: () => <div data-testid="block-editor" />,
    Dialog: (props: ComponentProps<typeof actual.Dialog>) => {
      dialogSpy(props);
      return <actual.Dialog {...props} />;
    },
  };
});

vi.mock('@/src/components/date/DateInput', () => ({
  DateInput: ({
    disabled,
    onValueChange,
    value,
  }: {
    disabled?: boolean;
    onValueChange: (value: string) => void;
    value: string;
  }) => (
    <input
      disabled={disabled}
      onChange={(event) => onValueChange(event.target.value)}
      value={value}
    />
  ),
}));

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({
    token: 'token-1',
    user: { id: 'user-1' },
  }),
}));

vi.mock('@/src/platform/media/use-media-upload', () => ({
  useMediaUpload: () => ({
    resolveFileUrl: vi.fn(),
    uploadFile: vi.fn(),
  }),
}));

vi.mock('../api/pms-api', () => ({
  createTaskListTask: vi.fn(),
  listSpaceMembers: vi.fn(),
  listTaskTemplates: vi.fn(),
}));

vi.mock('./TaskPickerModal', () => ({
  TaskPickerModal: (props: Record<string, unknown>) => {
    taskPickerModalSpy(props);
    return <div data-testid="parent-task-picker" />;
  },
}));

describe('NewTaskModal', () => {
  it('selects an app-owned task list without an outer container selector', () => {
    const onTaskListIdChange = vi.fn();
    render(
      <NewTaskModal
        isOpen
        onClose={vi.fn()}
        onTaskListIdChange={onTaskListIdChange}
        taskListId="list-alpha"
        taskListOptions={[
          { id: 'list-alpha', label: 'Alpha / Backlog' },
          { id: 'list-beta', label: 'Beta / Backlog' },
        ]}
        taskListStatuses={[]}
      />,
    );
    fireEvent.change(
      screen.getByRole('combobox', { name: 'pms.floating.taskList' }),
      { target: { value: 'list-beta' } },
    );
    expect(onTaskListIdChange).toHaveBeenCalledWith('list-beta');
    expect(
      screen.queryByRole('combobox', { name: 'common:labels.workspace' }),
    ).toBeNull();
  });

  it('keeps the deleted workspace selector out of PMS task modals', () => {
    render(
      <NewTaskModal
        isOpen
        onClose={vi.fn()}
        taskListId="list-1"
        taskListStatuses={[]}
      />,
    );

    expect(
      screen.queryByRole('combobox', { name: 'common:labels.workspace' }),
    ).toBeNull();
  });

  it('keeps accidental outside interactions from dismissing task content', () => {
    render(
      <NewTaskModal
        isOpen
        onClose={vi.fn()}
        taskListId="list-1"
        taskListStatuses={[]}
      />,
    );

    expect(dialogSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        dismissOnInteractOutside: false,
      }),
    );
  });

  it('ignores Escape while keeping the close button active', () => {
    const onClose = vi.fn();
    const widgetHostEscapeHandler = vi.fn();
    window.addEventListener('keydown', widgetHostEscapeHandler);
    try {
      render(
        <NewTaskModal
          isOpen
          onClose={onClose}
          taskListId="list-1"
          taskListStatuses={[]}
        />,
      );

      fireEvent.change(screen.getByRole('textbox', { name: 'pms.taskName' }), {
        target: { value: 'Draft task title' },
      });
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

      expect(onClose).not.toHaveBeenCalled();
      expect(widgetHostEscapeHandler).not.toHaveBeenCalled();
      expect(
        (
          screen.getByRole('textbox', {
            name: 'pms.taskName',
          }) as HTMLInputElement
        ).value,
      ).toBe('Draft task title');

      fireEvent.click(
        screen.getByRole('button', { name: 'common:actions.close' }),
      );
      expect(onClose).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener('keydown', widgetHostEscapeHandler);
    }
  });

  it('opens the parent task picker above a floating widget modal layer', () => {
    render(
      <NewTaskModal
        isOpen
        onClose={vi.fn()}
        parentPickerContentClassName="z-[122]"
        parentPickerOverlayClassName="z-[121]"
        taskListId="list-1"
        taskListStatuses={[]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /pms\.noParentTask/ }));

    expect(screen.getByTestId('parent-task-picker')).not.toBeNull();
    expect(taskPickerModalSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        contentClassName: 'z-[122]',
        fixedTaskListId: 'list-1',
        isOpen: true,
        layer: 'elevated',
        overlayClassName: 'z-[121]',
      }),
    );
  });
});
