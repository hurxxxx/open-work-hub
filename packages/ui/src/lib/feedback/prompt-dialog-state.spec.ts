import { describe, expect, it, vi } from 'vitest';

import {
  cancelCurrentPromptDialog,
  openPromptDialog,
  submitCurrentPromptDialog,
  type PromptDialogRequest,
} from './prompt-dialog-state';

function request(
  overrides: Partial<PromptDialogRequest> = {},
): PromptDialogRequest {
  return {
    title: 'Rename item',
    description: 'Choose a visible name.',
    placeholder: 'Item name',
    defaultValue: 'Current name',
    submitLabel: 'Save',
    cancelLabel: 'Cancel',
    resolve: vi.fn(),
    ...overrides,
  };
}

describe('prompt dialog state', () => {
  it('opens a prompt request without completing another request', () => {
    const nextRequest = request();

    const transition = openPromptDialog(null, nextRequest);

    expect(transition).toEqual({
      state: nextRequest,
      completion: null,
    });
  });

  it('replaces an open prompt request and completes the current request as cancelled', () => {
    const currentRequest = request({ title: 'First' });
    const nextRequest = request({ title: 'Second' });

    const transition = openPromptDialog(currentRequest, nextRequest);

    expect(transition.state).toBe(nextRequest);
    expect(transition.completion).toEqual({
      resolve: currentRequest.resolve,
      value: null,
    });
  });

  it('submits the current prompt value and closes the dialog', () => {
    const currentRequest = request();

    const transition = submitCurrentPromptDialog(currentRequest, 'New name');

    expect(transition.state).toBeNull();
    expect(transition.completion).toEqual({
      resolve: currentRequest.resolve,
      value: 'New name',
    });
  });

  it('cancels the current prompt and closes the dialog', () => {
    const currentRequest = request();

    const transition = cancelCurrentPromptDialog(currentRequest);

    expect(transition.state).toBeNull();
    expect(transition.completion).toEqual({
      resolve: currentRequest.resolve,
      value: null,
    });
  });

  it('ignores submit and cancel transitions when no request is open', () => {
    expect(submitCurrentPromptDialog(null, 'New name')).toEqual({
      state: null,
      completion: null,
    });
    expect(cancelCurrentPromptDialog(null)).toEqual({
      state: null,
      completion: null,
    });
  });
});
