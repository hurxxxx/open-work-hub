import type {
  ConversationListResponse,
  ConversationSummary,
} from './api/conversations-api';

export const CONVERSATION_LIST_LIMIT = 50;

export type ConversationDateGroupId =
  | 'historyToday'
  | 'historyYesterday'
  | 'historyOlder';

export interface ConversationDateGroup {
  id: ConversationDateGroupId;
  items: ConversationSummary[];
}

export interface ChatbotSidebarState {
  conversations: ConversationSummary[];
  nextCursor: string | null;
  isLoadingMore: boolean;
  error: string | null;
}

export type ChatbotSidebarAction =
  | { type: 'reset' }
  | {
      type: 'loadSuccess';
      items: ConversationSummary[];
      nextCursor: string | null;
    }
  | { type: 'loadFailure'; message: string }
  | { type: 'loadMoreStart' }
  | {
      type: 'loadMoreSuccess';
      items: ConversationSummary[];
      nextCursor: string | null;
    }
  | { type: 'loadMoreFailure'; message: string }
  | { type: 'deleteSuccess'; conversationId: string }
  | { type: 'renameSuccess'; conversation: ConversationSummary };

export const CHATBOT_SIDEBAR_INITIAL_STATE: ChatbotSidebarState = {
  conversations: [],
  nextCursor: null,
  isLoadingMore: false,
  error: null,
};

export type ListConversationsPage = (
  token: string,
  options: {
    limit: number;
    cursor?: string | null;
    scopeRef?: string;
    scopeResourceId?: string;
    workspaceSlug?: string | null;
  },
) => Promise<ConversationListResponse>;

export interface ConversationListScopeFilter {
  scopeRef?: string;
  scopeResourceId?: string;
  workspaceSlug?: string | null;
}

export function groupConversationsByDate(
  conversations: ConversationSummary[],
  now = new Date(),
): ConversationDateGroup[] {
  const groups: Record<ConversationDateGroupId, ConversationSummary[]> = {
    historyToday: [],
    historyYesterday: [],
    historyOlder: [],
  };
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart);
  yesterdayStart.setDate(todayStart.getDate() - 1);
  for (const conversation of conversations) {
    const updatedAt = new Date(conversation.updatedAt);
    if (updatedAt >= todayStart) {
      groups.historyToday.push(conversation);
    } else if (updatedAt >= yesterdayStart) {
      groups.historyYesterday.push(conversation);
    } else {
      groups.historyOlder.push(conversation);
    }
  }
  const visibleGroups: ConversationDateGroup[] = [];
  for (const id of Object.keys(groups) as ConversationDateGroupId[]) {
    if (groups[id].length > 0) {
      visibleGroups.push({ id, items: groups[id] });
    }
  }
  return visibleGroups;
}

export function filterConversations(
  conversations: ConversationSummary[],
  query: string,
  fallbackTitle: string,
): ConversationSummary[] {
  const normalizedQuery = query.trim();
  if (!normalizedQuery) {
    return conversations;
  }
  const normalizedSearch = normalizedQuery.toLocaleLowerCase();
  const next: ConversationSummary[] = [];
  for (const conversation of conversations) {
    const title = conversation.title || fallbackTitle;
    if (title.toLocaleLowerCase().includes(normalizedSearch)) {
      next.push(conversation);
    }
  }
  return next;
}

export function shouldAutoLoadMoreForSearch({
  filteredCount,
  hasMore,
  isLoadingMore,
  query,
}: {
  filteredCount: number;
  hasMore: boolean;
  isLoadingMore: boolean;
  query: string;
}): boolean {
  return (
    Boolean(query.trim()) && filteredCount === 0 && hasMore && !isLoadingMore
  );
}

export async function listConversationsWindow(
  listPage: ListConversationsPage,
  token: string,
  requestedLimit: number,
  scope: ConversationListScopeFilter = {},
): Promise<ConversationListResponse> {
  const items: ConversationSummary[] = [];
  let cursor: string | null = null;
  do {
    const response = await listPage(token, {
      limit: Math.min(CONVERSATION_LIST_LIMIT, requestedLimit - items.length),
      cursor,
      scopeRef: scope.scopeRef,
      scopeResourceId: scope.scopeResourceId,
      workspaceSlug: scope.workspaceSlug,
    });
    items.push(...response.items);
    cursor = response.nextCursor ?? null;
  } while (cursor && items.length < requestedLimit);
  return { items, nextCursor: cursor };
}

export function chatbotSidebarReducer(
  state: ChatbotSidebarState,
  action: ChatbotSidebarAction,
): ChatbotSidebarState {
  switch (action.type) {
    case 'reset':
      return CHATBOT_SIDEBAR_INITIAL_STATE;
    case 'loadSuccess':
      return {
        conversations: action.items,
        nextCursor: action.nextCursor,
        isLoadingMore: false,
        error: null,
      };
    case 'loadFailure':
      return {
        conversations: [],
        nextCursor: null,
        isLoadingMore: false,
        error: action.message,
      };
    case 'loadMoreStart':
      return { ...state, isLoadingMore: true };
    case 'loadMoreSuccess':
      return {
        conversations: [...state.conversations, ...action.items],
        nextCursor: action.nextCursor,
        isLoadingMore: false,
        error: null,
      };
    case 'loadMoreFailure':
      return { ...state, isLoadingMore: false, error: action.message };
    case 'deleteSuccess':
      return {
        ...state,
        conversations: state.conversations.filter(
          (item) => item.id !== action.conversationId,
        ),
      };
    case 'renameSuccess':
      return {
        ...state,
        conversations: state.conversations.map((item) =>
          item.id === action.conversation.id ? action.conversation : item,
        ),
      };
    default:
      return state;
  }
}
