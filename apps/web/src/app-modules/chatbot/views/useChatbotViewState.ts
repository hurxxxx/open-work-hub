import { useCallback, useReducer } from 'react';

import type { ChatTurn } from './chat/MessageBubble';
import type { ChatbotConversationScopeInfo } from './chatbot-view-model';

type ScopeInfo = ChatbotConversationScopeInfo;

type ApprovalActionKind = 'approve' | 'reject' | 'abandon' | 'resume';

export type ChatbotViewStateUpdater<T> = T | ((current: T) => T);
export type ChatbotViewStatePatch = Partial<ChatbotViewState>;
export type ChatbotViewStatePatchUpdater =
  | ChatbotViewStatePatch
  | ((current: ChatbotViewState) => ChatbotViewStatePatch);

export interface ChatbotViewState {
  turns: ChatTurn[];
  input: string;
  editingTurnId: string | null;
  editingText: string;
  chatError: string | null;
  approvalError: string | null;
  failedPromptRecovery: string;
  forceFollowKey: number;
  activeConversationId: string | null;
  isLoadingConversation: boolean;
  scopeInfo: ScopeInfo | null;
  approvalAction: {
    approvalId: string;
    kind: ApprovalActionKind;
  } | null;
  showInsightHint: boolean;
  pendingDraftSearchCleanup: boolean;
}

type ChatbotViewStateAction =
  | { type: 'patch'; value: ChatbotViewStatePatchUpdater }
  | ChatbotViewStateFieldAction;

type ChatbotViewStateField = keyof ChatbotViewState;
type ChatbotViewStateFieldAction = {
  [Field in ChatbotViewStateField]: {
    type: Field;
    value: ChatbotViewStateUpdater<ChatbotViewState[Field]>;
  };
}[ChatbotViewStateField];

type ChatbotViewStateSetter<T extends ChatbotViewStateField> =
  ChatbotViewStateUpdater<ChatbotViewState[T]>;

export const INITIAL_CHATBOT_VIEW_STATE: ChatbotViewState = {
  turns: [],
  input: '',
  editingTurnId: null,
  editingText: '',
  chatError: null,
  approvalError: null,
  failedPromptRecovery: '',
  forceFollowKey: 0,
  activeConversationId: null,
  isLoadingConversation: false,
  scopeInfo: null,
  approvalAction: null,
  showInsightHint: false,
  pendingDraftSearchCleanup: false,
};

function applyChatbotViewStateField(
  state: ChatbotViewState,
  action: ChatbotViewStateFieldAction,
): ChatbotViewState {
  const currentValue = state[action.type];
  const nextValue =
    typeof action.value === 'function'
      ? (action.value as (current: typeof currentValue) => typeof currentValue)(
          currentValue,
        )
      : action.value;

  return {
    ...state,
    [action.type]: nextValue,
  };
}

export function aiViewStateReducer(
  state: ChatbotViewState,
  action: ChatbotViewStateAction,
): ChatbotViewState {
  switch (action.type) {
    case 'patch': {
      const patch =
        typeof action.value === 'function' ? action.value(state) : action.value;
      return {
        ...state,
        ...patch,
      };
    }
    default:
      return applyChatbotViewStateField(state, action);
  }
}

function useChatbotViewStateSetter<T extends ChatbotViewStateField>(
  dispatch: (action: ChatbotViewStateAction) => void,
  type: T,
) {
  return useCallback(
    (value: ChatbotViewStateSetter<T>) => {
      dispatch({ type, value } as ChatbotViewStateFieldAction);
    },
    [dispatch, type],
  );
}

export function useChatbotViewState() {
  const [state, dispatch] = useReducer(
    aiViewStateReducer,
    INITIAL_CHATBOT_VIEW_STATE,
  );
  return {
    state,
    setTurns: useChatbotViewStateSetter(dispatch, 'turns'),
    patchViewState: useCallback((value: ChatbotViewStatePatchUpdater) => {
      dispatch({ type: 'patch', value });
    }, []),
    setInput: useChatbotViewStateSetter(dispatch, 'input'),
    setEditingTurnId: useChatbotViewStateSetter(dispatch, 'editingTurnId'),
    setEditingText: useChatbotViewStateSetter(dispatch, 'editingText'),
    setChatError: useChatbotViewStateSetter(dispatch, 'chatError'),
    setApprovalError: useChatbotViewStateSetter(dispatch, 'approvalError'),
    setFailedPromptRecovery: useChatbotViewStateSetter(
      dispatch,
      'failedPromptRecovery',
    ),
    setForceFollowKey: useChatbotViewStateSetter(dispatch, 'forceFollowKey'),
    setActiveConversationId: useChatbotViewStateSetter(
      dispatch,
      'activeConversationId',
    ),
    setIsLoadingConversation: useChatbotViewStateSetter(
      dispatch,
      'isLoadingConversation',
    ),
    setScopeInfo: useChatbotViewStateSetter(dispatch, 'scopeInfo'),
    setApprovalAction: useChatbotViewStateSetter(dispatch, 'approvalAction'),
    setShowInsightHint: useChatbotViewStateSetter(dispatch, 'showInsightHint'),
    setPendingDraftSearchCleanup: useChatbotViewStateSetter(
      dispatch,
      'pendingDraftSearchCleanup',
    ),
  };
}
