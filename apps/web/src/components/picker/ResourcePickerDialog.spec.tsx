import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ResourcePickerDialog } from './ResourcePickerDialog';

const dialogSpy = vi.hoisted(() => vi.fn());

vi.mock('@open-alm/ui', () => ({
  Button: ({
    children,
    ...props
  }: ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
  Dialog: ({
    children,
    contentClassName,
    open,
    overlayClassName,
  }: {
    children: ReactNode;
    contentClassName?: string;
    open: boolean;
    overlayClassName?: string;
  }) => {
    dialogSpy({ contentClassName, overlayClassName });
    return open ? <div data-testid="resource-picker">{children}</div> : null;
  },
  InlineNotice: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
}));

describe('ResourcePickerDialog', () => {
  it('passes explicit layer classes to the underlying dialog', () => {
    render(
      <ResourcePickerDialog
        closeLabel="Close"
        contentClassName="z-[122]"
        description="Pick a resource"
        emptyLabel="Empty"
        getItemId={(item) => item.id}
        isOpen
        items={[]}
        onClose={vi.fn()}
        onPick={vi.fn()}
        overlayClassName="z-[121]"
        renderItem={(item) => item.label}
        title="Picker"
      />,
    );

    expect(screen.getByTestId('resource-picker')).not.toBeNull();
    expect(dialogSpy).toHaveBeenCalledWith({
      contentClassName: 'z-[122]',
      overlayClassName: 'z-[121]',
    });
  });
});
