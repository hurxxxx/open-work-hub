import type {
  ArtifactBuffer,
  ChatStreamStatus,
  PendingApproval,
  ToolCallBuffer,
} from '../../api/agent-events';

export interface ChatTurn {
  id: string;
  seq?: number;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  reasoningStatus?: ChatStreamStatus;
  finishReason?:
    | 'stop'
    | 'length'
    | 'cancelled'
    | 'error'
    | 'awaiting_approval'
    | null;
  provider?: string;
  policy?: string | null;
  chosenPool?: 'local' | 'external' | null;
  decisionReason?: string | null;
  forcedLocal?: boolean;
  piiHits?: string[];
  responseStatus?: Exclude<ChatStreamStatus, 'idle' | 'streaming'>;
  toolCalls?: ToolCallBuffer[];
  pendingApprovals?: PendingApproval[];
  artifacts?: ArtifactBuffer[];
}
