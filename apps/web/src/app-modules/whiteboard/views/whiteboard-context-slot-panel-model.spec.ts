import { describe, expect, it } from 'vitest';

import type { WhiteboardDetail } from '../api/whiteboard-api';
import {
  INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE,
  buildWhiteboardContextSlotAttachPayload,
  buildWhiteboardContextSlotCreatePayload,
  getWhiteboardContextSlotExcludeIds,
  whiteboardContextSlotPanelReducer,
  type WhiteboardContextRef,
} from './whiteboard-context-slot-panel-model';

function board(id: string): WhiteboardDetail {
  return {
    id,
    title: `Board ${id}`,
    ownership_kind: 'personal',
    company_visible: false,
    source_app: 'whiteboard',
    source_type: 'whiteboard',
    source_id: id,
    source_kind: 'native',
    source_ref: null,
    generation_kind: 'manual',
    location_label: 'Personal',
    target_label: '',
    primary_target: null,
    targets: [],
    source_badge: '',
    source_deeplink: null,
    created_by_id: 'user-1',
    created_by_name: 'Member',
    created_at: '2026-09-08T00:00:00Z',
    updated_at: '2026-09-08T00:00:00Z',
    trashed_at: null,
    is_favorite: false,
    is_private: true,
    last_viewed_at: null,
    can_view: true,
    can_edit: true,
    can_share: true,
    can_manage: true,
    scene: { elements: [], appState: {}, files: {} },
  };
}

const context: WhiteboardContextRef = {
  app: 'pms',
  type: 'task',
  id: 'task-1',
};

describe('whiteboard-context-slot-panel-model', () => {
  it('tracks load and picker transitions', () => {
    const loading = whiteboardContextSlotPanelReducer(
      { ...INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE, error: 'Previous' },
      { type: 'load-started' },
    );
    expect(loading.loading).toBe(true);
    expect(loading.error).toBeNull();

    const loaded = whiteboardContextSlotPanelReducer(loading, {
      type: 'load-succeeded',
      item: board('board-1'),
    });
    expect(loaded.loading).toBe(false);
    expect(loaded.item?.id).toBe('board-1');

    const failed = whiteboardContextSlotPanelReducer(loaded, {
      type: 'load-failed',
      error: 'Load failed',
    });
    expect(failed.loading).toBe(false);
    expect(failed.item).toBeNull();
    expect(failed.error).toBe('Load failed');

    const opened = whiteboardContextSlotPanelReducer(failed, {
      type: 'picker-opened',
    });
    expect(opened.pickerOpen).toBe(true);

    const closed = whiteboardContextSlotPanelReducer(opened, {
      type: 'picker-closed',
    });
    expect(closed.pickerOpen).toBe(false);
  });

  it('tracks create, attach, update, and detach transitions', () => {
    const creating = whiteboardContextSlotPanelReducer(
      { ...INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE, error: 'Previous' },
      { type: 'create-started' },
    );
    expect(creating.busy).toBe(true);
    expect(creating.error).toBeNull();

    const created = whiteboardContextSlotPanelReducer(creating, {
      type: 'create-succeeded',
      item: board('created'),
    });
    expect(created.busy).toBe(false);
    expect(created.item?.id).toBe('created');

    const attachFailed = whiteboardContextSlotPanelReducer(created, {
      type: 'attach-failed',
      error: 'Attach failed',
    });
    expect(attachFailed.busy).toBe(false);
    expect(attachFailed.error).toBe('Attach failed');

    const attached = whiteboardContextSlotPanelReducer(attachFailed, {
      type: 'attach-succeeded',
      item: board('attached'),
    });
    expect(attached.item?.id).toBe('attached');

    const updated = whiteboardContextSlotPanelReducer(attached, {
      type: 'update-succeeded',
      item: board('updated'),
    });
    expect(updated.item?.id).toBe('updated');

    const detaching = whiteboardContextSlotPanelReducer(updated, {
      type: 'detach-started',
    });
    expect(detaching.busy).toBe(true);
    expect(detaching.error).toBeNull();

    const detached = whiteboardContextSlotPanelReducer(detaching, {
      type: 'detach-succeeded',
    });
    expect(detached.busy).toBe(false);
    expect(detached.item).toBeNull();

    const detachFailed = whiteboardContextSlotPanelReducer(detached, {
      type: 'detach-failed',
      error: 'Detach failed',
    });
    expect(detachFailed.busy).toBe(false);
    expect(detachFailed.error).toBe('Detach failed');
  });

  it('builds create and attach request payloads from the context', () => {
    expect(
      buildWhiteboardContextSlotCreatePayload(context, 'Task whiteboard'),
    ).toEqual({
      ...context,
      title: 'Task whiteboard',
    });

    expect(
      buildWhiteboardContextSlotAttachPayload(context, 'whiteboard-1'),
    ).toEqual({
      ...context,
      whiteboard_id: 'whiteboard-1',
    });
  });

  it('projects picker exclude ids from the attached board', () => {
    expect(getWhiteboardContextSlotExcludeIds(null)).toEqual([]);
    expect(getWhiteboardContextSlotExcludeIds(board('whiteboard-1'))).toEqual([
      'whiteboard-1',
    ]);
  });
});
