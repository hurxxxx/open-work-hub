import { fireEvent, render } from '@testing-library/react';

import { Button } from './primitives/button';
import { DataTable } from './data-display/data-table';
import { DetailDrawer } from './layout/detail-drawer';
import { Dialog } from './primitives/dialog';
import {
  ToastProvider,
  ToastViewport,
  useToast,
} from './providers/toast-provider';

describe('shared ui', () => {
  it('renders button variants', () => {
    const { getByText } = render(<Button variant="primary">Primary</Button>);
    expect(getByText('Primary')).toBeTruthy();
  });

  it('renders empty state for data table with no rows', () => {
    const { getByText } = render(
      <DataTable
        columns={[{ accessorKey: 'name', header: 'Name' }]}
        rows={[] as Array<{ name: string }>}
      />,
    );

    expect(getByText(/No results/i)).toBeTruthy();
  });

  it('renders loading state for data table', () => {
    const { container } = render(
      <DataTable
        columns={[{ accessorKey: 'name', header: 'Name' }]}
        rows={[{ name: 'Row' }]}
        loading
      />,
    );

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders drawer content when open', () => {
    const { getByText } = render(
      <DetailDrawer
        open
        onOpenChange={() => undefined}
        title="Document details"
        description="Drawer body"
      >
        <div>Evidence block</div>
      </DetailDrawer>,
    );

    expect(getByText(/Document details/i)).toBeTruthy();
    expect(getByText(/Evidence block/i)).toBeTruthy();
  });

  it('opens dialogs without descriptions without emitting accessibility warnings', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    const { getByText } = render(
      <Dialog open onOpenChange={() => undefined} title="Quick create">
        <div>Body content</div>
      </Dialog>,
    );

    expect(getByText(/Quick create/i)).toBeTruthy();
    expect(getByText(/Body content/i)).toBeTruthy();
    expect(errorSpy).not.toHaveBeenCalled();

    errorSpy.mockRestore();
  });

  it('shows toast notifications through the shared provider', () => {
    function Demo() {
      const toast = useToast();

      return (
        <Button onClick={() => toast.success('Saved', 'Toast from shared provider')}>
          Trigger toast
        </Button>
      );
    }

    const { getByText } = render(
      <ToastProvider>
        <Demo />
        <ToastViewport />
      </ToastProvider>,
    );

    fireEvent.click(getByText(/Trigger toast/i));
    expect(getByText(/Saved/i)).toBeTruthy();
    expect(getByText(/Toast from shared provider/i)).toBeTruthy();
  });
});
