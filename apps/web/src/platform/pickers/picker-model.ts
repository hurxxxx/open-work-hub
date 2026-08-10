export type PickerState<TItem> = {
  items: TItem[];
  query: string;
  loading: boolean;
  submittingId: string | null;
  error: string | null;
};

export type PickerAction<TItem> =
  | { type: 'reset' }
  | { type: 'load'; resetQuery?: boolean }
  | { type: 'loaded'; items: TItem[] }
  | { type: 'failed'; message: string }
  | { type: 'query'; value: string }
  | { type: 'submit'; itemId: string }
  | { type: 'submit-failed'; message: string; clearSubmitting?: boolean }
  | { type: 'submit-finished' };

export type PickerProjectionOptions<TItem> = {
  items: readonly TItem[];
  excludeIds?: readonly string[];
  getItemId: (item: TItem) => string;
  limit?: number;
  matchesQuery?: (item: TItem, normalizedQuery: string) => boolean;
  query?: string;
};

export function createInitialPickerState<TItem>(): PickerState<TItem> {
  return {
    items: [],
    query: '',
    loading: false,
    submittingId: null,
    error: null,
  };
}

export function pickerReducer<TItem>(
  state: PickerState<TItem>,
  action: PickerAction<TItem>,
  initialState: PickerState<TItem> = createInitialPickerState<TItem>(),
): PickerState<TItem> {
  switch (action.type) {
    case 'reset':
      return initialState;
    case 'load':
      return {
        ...state,
        query: action.resetQuery ? '' : state.query,
        loading: true,
        submittingId: null,
        error: null,
      };
    case 'loaded':
      return {
        ...state,
        items: action.items,
        loading: false,
      };
    case 'failed':
      return {
        ...state,
        items: [],
        loading: false,
        error: action.message,
      };
    case 'query':
      return {
        ...state,
        query: action.value,
      };
    case 'submit':
      return {
        ...state,
        submittingId: action.itemId,
        error: null,
      };
    case 'submit-failed':
      return {
        ...state,
        error: action.message,
        submittingId: action.clearSubmitting === false ? state.submittingId : null,
      };
    case 'submit-finished':
      return {
        ...state,
        submittingId: null,
      };
  }
}

export function projectPickerItems<TItem>({
  items,
  excludeIds = [],
  getItemId,
  limit = 50,
  matchesQuery,
  query = '',
}: PickerProjectionOptions<TItem>): TItem[] {
  const excluded = new Set(excludeIds);
  const normalizedQuery = query.trim().toLowerCase();
  return items.reduce<TItem[]>((result, item) => {
    if (result.length >= limit || excluded.has(getItemId(item))) {
      return result;
    }
    if (
      normalizedQuery
      && matchesQuery
      && !matchesQuery(item, normalizedQuery)
    ) {
      return result;
    }
    result.push(item);
    return result;
  }, []);
}
