import type { PmsSpace, PmsTaskList } from '../api/pms-api';

export const PMS_SPACE_MEMBERS_CHANGED_EVENT = 'pms:space-members-changed';
export const PMS_SPACE_CHANGED_EVENT = 'pms:space-changed';
export const PMS_SPACE_ORDER_CHANGED_EVENT = 'pms:space-order-changed';
export const PMS_TASK_LIST_CHANGED_EVENT = 'pms:task-list-changed';

export interface PmsSpaceMembersChangedDetail {
  spaceId: string;
}

export interface PmsSpaceOrderChangedDetail {
  spaceId: string;
  listChanges: Array<{
    id: string;
    folder_id: string | null;
    sort_order: number;
  }>;
  docChanges: Array<{ id: string; sort_order: number }>;
}

export type PmsSpaceChangedDetail =
  | { type: 'updated'; space: PmsSpace }
  | { type: 'deleted'; spaceId: string };

export type PmsTaskListChangedDetail =
  | { type: 'updated'; taskList: PmsTaskList }
  | { type: 'deleted'; taskListId: string };

export function dispatchPmsSpaceMembersChanged(spaceId: string): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<PmsSpaceMembersChangedDetail>(
      PMS_SPACE_MEMBERS_CHANGED_EVENT,
      {
        detail: { spaceId },
      },
    ),
  );
}

export function dispatchPmsSpaceChanged(detail: PmsSpaceChangedDetail): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<PmsSpaceChangedDetail>(PMS_SPACE_CHANGED_EVENT, {
      detail,
    }),
  );
}

export function dispatchPmsSpaceOrderChanged(
  detail: PmsSpaceOrderChangedDetail,
): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<PmsSpaceOrderChangedDetail>(PMS_SPACE_ORDER_CHANGED_EVENT, {
      detail,
    }),
  );
}

export function dispatchPmsTaskListChanged(
  detail: PmsTaskListChangedDetail,
): void {
  if (typeof window === 'undefined') return;

  window.dispatchEvent(
    new CustomEvent<PmsTaskListChangedDetail>(PMS_TASK_LIST_CHANGED_EVENT, {
      detail,
    }),
  );
}
