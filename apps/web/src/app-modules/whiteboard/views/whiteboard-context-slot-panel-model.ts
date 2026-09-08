import type {
  WhiteboardDetail,
  WhiteboardContextSlotCreatePayload,
  WhiteboardContextSlotAttachPayload,
} from '../api/whiteboard-api';

export interface WhiteboardContextRef {
  app: string;
  type: string;
  id: string;
}

export interface WhiteboardContextSlotPanelState {
  item: WhiteboardDetail | null;
  loading: boolean;
  busy: boolean;
  pickerOpen: boolean;
  error: string | null;
}

export type WhiteboardContextSlotPanelAction =
  | { type: 'load-started' }
  | { type: 'load-succeeded'; item: WhiteboardDetail | null }
  | { type: 'load-failed'; error: string }
  | { type: 'create-started' }
  | { type: 'operation-cancelled' }
  | { type: 'create-succeeded'; item: WhiteboardDetail }
  | { type: 'create-failed'; error: string }
  | { type: 'attach-started' }
  | { type: 'attach-succeeded'; item: WhiteboardDetail }
  | { type: 'attach-failed'; error: string }
  | { type: 'detach-started' }
  | { type: 'detach-succeeded' }
  | { type: 'detach-failed'; error: string }
  | { type: 'update-started' }
  | { type: 'update-succeeded'; item: WhiteboardDetail }
  | { type: 'update-failed'; error: string }
  | { type: 'picker-opened' }
  | { type: 'picker-closed' };

export const INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE: WhiteboardContextSlotPanelState =
  {
    item: null,
    loading: false,
    busy: false,
    pickerOpen: false,
    error: null,
  };

export function whiteboardContextSlotPanelReducer(
  state: WhiteboardContextSlotPanelState,
  action: WhiteboardContextSlotPanelAction,
): WhiteboardContextSlotPanelState {
  switch (action.type) {
    case 'operation-cancelled':
      return { ...state, busy: false };
    case 'load-started':
      return { ...state, loading: true, error: null };
    case 'load-succeeded':
      return { ...state, item: action.item, loading: false };
    case 'load-failed':
      return { ...state, item: null, loading: false, error: action.error };
    case 'create-started':
    case 'attach-started':
    case 'detach-started':
    case 'update-started':
      return { ...state, busy: true, error: null };
    case 'create-succeeded':
    case 'attach-succeeded':
    case 'update-succeeded':
      return { ...state, item: action.item, busy: false };
    case 'detach-succeeded':
      return { ...state, item: null, busy: false };
    case 'create-failed':
    case 'attach-failed':
    case 'detach-failed':
    case 'update-failed':
      return { ...state, busy: false, error: action.error };
    case 'picker-opened':
      return { ...state, pickerOpen: true };
    case 'picker-closed':
      return { ...state, pickerOpen: false };
  }
}

export function buildWhiteboardContextSlotCreatePayload(
  context: WhiteboardContextRef,
  title: string,
  acknowledged: boolean,
): WhiteboardContextSlotCreatePayload {
  return { ...context, title, company_admin_read_acknowledged: acknowledged };
}

export function buildWhiteboardContextSlotAttachPayload(
  context: WhiteboardContextRef,
  whiteboardId: string,
  acknowledged: boolean,
): WhiteboardContextSlotAttachPayload {
  return {
    ...context,
    whiteboard_id: whiteboardId,
    company_admin_read_acknowledged: acknowledged,
  };
}

export function getWhiteboardContextSlotExcludeIds(
  item: WhiteboardDetail | null,
): string[] {
  return item ? [item.id] : [];
}
