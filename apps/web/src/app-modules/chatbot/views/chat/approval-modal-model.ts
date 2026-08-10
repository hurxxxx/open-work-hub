import type { AiApprovalStatusResponse } from '../../api/chatbot-api';

export const APPROVAL_REJECTION_REASON_MAX_LENGTH = 140;

export type ApprovalToolLabelKey =
  | 'ai.approval.toolPms'
  | 'ai.approval.toolPlanner'
  | 'ai.approval.toolDocs'
  | 'ai.approval.toolMeeting'
  | 'ai.approval.toolDefault';

export interface ApprovalModalState {
  rejectReason: string;
  details: AiApprovalStatusResponse | null;
  detailsError: string | null;
  loadingDetails: boolean;
}

export type ApprovalModalAction =
  | { type: 'load-details' }
  | { type: 'details-loaded'; details: AiApprovalStatusResponse }
  | { type: 'details-failed'; message: string }
  | { type: 'reject-reason'; value: string };

export const INITIAL_APPROVAL_MODAL_STATE: ApprovalModalState = {
  rejectReason: '',
  details: null,
  detailsError: null,
  loadingDetails: false,
};

export function approvalToolLabelKey(toolName: string): ApprovalToolLabelKey {
  if (toolName.startsWith('pms.')) {
    return 'ai.approval.toolPms';
  }
  if (toolName.startsWith('planner.')) {
    return 'ai.approval.toolPlanner';
  }
  if (toolName.startsWith('docs.')) {
    return 'ai.approval.toolDocs';
  }
  if (toolName.startsWith('meeting.')) {
    return 'ai.approval.toolMeeting';
  }
  return 'ai.approval.toolDefault';
}

export function formatApprovalArgumentsJson(
  raw: string | null | undefined,
): string {
  if (!raw) {
    return '{}';
  }
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

export function limitApprovalRejectionReason(value: string): string {
  return value.slice(0, APPROVAL_REJECTION_REASON_MAX_LENGTH);
}

export function approvalModalReducer(
  state: ApprovalModalState,
  action: ApprovalModalAction,
): ApprovalModalState {
  switch (action.type) {
    case 'load-details':
      return {
        ...state,
        rejectReason: '',
        details: null,
        detailsError: null,
        loadingDetails: true,
      };
    case 'details-loaded':
      return {
        ...state,
        details: action.details,
        loadingDetails: false,
      };
    case 'details-failed':
      return {
        ...state,
        details: null,
        detailsError: action.message,
        loadingDetails: false,
      };
    case 'reject-reason':
      return {
        ...state,
        rejectReason: limitApprovalRejectionReason(action.value),
      };
  }
}
