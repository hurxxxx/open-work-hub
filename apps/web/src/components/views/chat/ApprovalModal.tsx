import type { PendingApproval } from '@/src/domains/ai/agent-events';

export interface ApprovalModalProps {
  approval: PendingApproval;
}

/**
 * Placeholder for Phase 4 approval flow. Props shape is fixed; Phase 4 will
 * add the modal UI + approve/reject callbacks without touching the hook or
 * envelope contract.
 */
export function ApprovalModal(_: ApprovalModalProps) {
  return null;
}
