import { describe, expect, it, vi } from 'vitest';

import {
  dispatchPmsSpaceOrderChanged,
  PMS_SPACE_ORDER_CHANGED_EVENT,
  type PmsSpaceOrderChangedDetail,
} from './pms-events';

describe('PMS events', () => {
  it('dispatches persisted order changes to mounted PMS surfaces', () => {
    const listener = vi.fn((event: Event) => {
      return (event as CustomEvent<PmsSpaceOrderChangedDetail>).detail;
    });
    window.addEventListener(PMS_SPACE_ORDER_CHANGED_EVENT, listener);

    dispatchPmsSpaceOrderChanged({
      spaceId: 'space-1',
      listChanges: [{ id: 'list-1', folder_id: 'folder-1', sort_order: 2 }],
      docChanges: [{ id: 'doc-1', sort_order: 3 }],
    });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.results[0]?.value).toEqual({
      spaceId: 'space-1',
      listChanges: [{ id: 'list-1', folder_id: 'folder-1', sort_order: 2 }],
      docChanges: [{ id: 'doc-1', sort_order: 3 }],
    });
    window.removeEventListener(PMS_SPACE_ORDER_CHANGED_EVENT, listener);
  });
});
