import { describe, expect, it, vi } from 'vitest';

import {
  cancelCurrentDialog,
  confirmCurrentDialog,
  openConfirmDialog,
  type ConfirmDialogRequest,
} from './confirm-dialog-state';

function request(
  overrides: Partial<ConfirmDialogRequest> = {},
): ConfirmDialogRequest {
  return {
    title: 'Delete item',
    description: 'This cannot be undone.',
    confirmLabel: 'Delete',
    cancelLabel: 'Cancel',
    resolve: vi.fn(),
    ...overrides,
  };
}

describe('confirm dialog state', () => {
  it('opens a confirm request without completing another request', () => {
    const nextRequest = request();

    const transition = openConfirmDialog(null, nextRequest);

    expect(transition).toEqual({
      state: nextRequest,
      completion: null,
    });
  });

  it('replaces an open confirm request and completes the current request as cancelled', () => {
    const currentRequest = request({ title: 'First' });
    const nextRequest = request({ title: 'Second' });

    const transition = openConfirmDialog(currentRequest, nextRequest);

    expect(transition.state).toBe(nextRequest);
    expect(transition.completion).toEqual({
      resolve: currentRequest.resolve,
      value: false,
    });
  });

  it('confirms the current request and closes the dialog', () => {
    const currentRequest = request();

    const transition = confirmCurrentDialog(currentRequest);

    expect(transition.state).toBeNull();
    expect(transition.completion).toEqual({
      resolve: currentRequest.resolve,
      value: true,
    });
  });

  it('cancels the current request and closes the dialog', () => {
    const currentRequest = request();

    const transition = cancelCurrentDialog(currentRequest);

    expect(transition.state).toBeNull();
    expect(transition.completion).toEqual({
      resolve: currentRequest.resolve,
      value: false,
    });
  });

  it('ignores confirm and cancel transitions when no request is open', () => {
    expect(confirmCurrentDialog(null)).toEqual({
      state: null,
      completion: null,
    });
    expect(cancelCurrentDialog(null)).toEqual({
      state: null,
      completion: null,
    });
  });
});
