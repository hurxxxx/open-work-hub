import { describe, expect, it, vi } from 'vitest';

import type { DmThread } from '../api/dm-api';
import {
  currentDmReadPresenceFromBrowser,
  markDmThreadReadAndApply,
  markVisibleDmThreadReadAndApply,
} from './dm-read-receipts';

describe('dm read receipts', () => {
  it('reads focus and visibility from the browser adapter', () => {
    expect(
      currentDmReadPresenceFromBrowser({
        visibilityState: 'visible',
        hasFocus: () => true,
      }),
    ).toEqual({ visible: true, focused: true });
    expect(
      currentDmReadPresenceFromBrowser({
        visibilityState: 'hidden',
        hasFocus: () => true,
      }),
    ).toEqual({ visible: false, focused: true });
  });

  it('marks a thread read and applies the returned thread', async () => {
    const markedThread = thread({ id: 'c1', unread_count: 0 });
    const markThreadRead = vi.fn(async () => markedThread);
    const onThreadRead = vi.fn();

    await expect(
      markDmThreadReadAndApply({
        conversationId: 'c1',
        markThreadRead,
        onThreadRead,
        token: 'token-1',
      }),
    ).resolves.toBe(markedThread);

    expect(markThreadRead).toHaveBeenCalledWith('token-1', 'c1');
    expect(onThreadRead).toHaveBeenCalledWith(markedThread);
  });

  it('no-ops read receipts without auth, selected thread, or visible focus', async () => {
    const markThreadRead = vi.fn(async () => thread());
    const onThreadRead = vi.fn();

    for (const input of [
      { token: null, selectedThreadId: 'c1', visible: true, focused: true },
      { token: 'token-1', selectedThreadId: '', visible: true, focused: true },
      { token: 'token-1', selectedThreadId: 'c1', visible: false, focused: true },
      { token: 'token-1', selectedThreadId: 'c1', visible: true, focused: false },
    ]) {
      await expect(
        markVisibleDmThreadReadAndApply({
          markThreadRead,
          onThreadRead,
          presence: {
            visible: input.visible,
            focused: input.focused,
          },
          selectedThreadId: input.selectedThreadId,
          token: input.token,
        }),
      ).resolves.toBeNull();
    }

    expect(markThreadRead).not.toHaveBeenCalled();
    expect(onThreadRead).not.toHaveBeenCalled();
  });
});

function thread(overrides: Partial<DmThread> = {}): DmThread {
  return {
    id: 'c1',
    conversation_type: 'direct',
    thread_type: 'direct',
    title: null,
    display_name: 'User One',
    other_user: null,
    participants: [],
    participant_count: 2,
    last_message: null,
    unread_count: 1,
    last_read_message_id: null,
    muted_at: null,
    created_by_id: 'u1',
    created_at: '2026-05-20T00:00:00.000Z',
    updated_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}
