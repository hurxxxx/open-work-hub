import { useCallback, useEffect, useReducer, useRef } from 'react';
import { i18n } from '@/src/platform/i18n';

import {
  archiveLearningPageNote,
  fetchLearningPageNoteDetail,
  fetchMyLearningPageNote,
  LearningNotesApiError,
  listLearningPageNotes,
  restoreLearningPageNote,
  upsertMyLearningPageNote,
} from './learning-notes-api';
import type {
  LearningPageNoteDetail,
  LearningPageNoteListItem,
  LearningPageNoteUpsertPayload,
} from './types';

export type LoadStatus = 'idle' | 'loading' | 'ready' | 'error';

interface LearningPageNotesListState {
  status: LoadStatus;
  items: LearningPageNoteListItem[];
  error: string | null;
  reloadToken: number;
}

type LearningPageNotesListLoadedAction = {
  type: 'loaded';
  items: LearningPageNoteListItem[];
};
type LearningPageNotesListAction =
  | LearningNotesLoadAction
  | LearningPageNotesListLoadedAction
  | { type: 'refresh' };

const INITIAL_LEARNING_PAGE_NOTES_LIST_STATE: LearningPageNotesListState = {
  status: 'idle',
  items: [],
  error: null,
  reloadToken: 0,
};

function learningPageNotesListReducer(
  state: LearningPageNotesListState,
  action: LearningPageNotesListAction,
): LearningPageNotesListState {
  switch (action.type) {
    case 'idle':
      return markLearningNotesIdle(state, { items: [] });
    case 'loading':
      return markLearningNotesLoading(state);
    case 'loaded':
      return markLearningNotesReady(state, { items: action.items });
    case 'failed':
      return markLearningNotesFailed(state, action.message);
    case 'refresh':
      return refreshLearningNotesState(state);
    default:
      return state;
  }
}

interface MyLearningPageNoteState {
  status: LoadStatus;
  note: LearningPageNoteDetail | null;
  error: string | null;
  saving: boolean;
  reloadToken: number;
}

type LearningPageNoteLoadedAction = {
  type: 'loaded';
  note: LearningPageNoteDetail | null;
};
type MyLearningPageNoteAction =
  | LearningNotesLoadAction
  | LearningPageNoteLoadedAction
  | { type: 'refresh' }
  | { type: 'savingStarted' }
  | { type: 'savingFinished' };

const INITIAL_MY_LEARNING_PAGE_NOTE_STATE: MyLearningPageNoteState = {
  status: 'idle',
  note: null,
  error: null,
  saving: false,
  reloadToken: 0,
};

function myLearningPageNoteReducer(
  state: MyLearningPageNoteState,
  action: MyLearningPageNoteAction,
): MyLearningPageNoteState {
  switch (action.type) {
    case 'idle':
      return markLearningNotesIdle(state, { note: null });
    case 'loading':
      return markLearningNotesLoading(state);
    case 'loaded':
      return markLearningNotesReady(state, { note: action.note });
    case 'failed':
      return markLearningNotesFailed(state, action.message);
    case 'refresh':
      return refreshLearningNotesState(state);
    case 'savingStarted':
      return {
        ...state,
        saving: true,
      };
    case 'savingFinished':
      return {
        ...state,
        saving: false,
      };
    default:
      return state;
  }
}

interface LearningPageNoteDetailState {
  status: LoadStatus;
  note: LearningPageNoteDetail | null;
  error: string | null;
}

type LearningPageNoteDetailAction =
  | LearningNotesLoadAction
  | LearningPageNoteLoadedAction;

const INITIAL_LEARNING_PAGE_NOTE_DETAIL_STATE: LearningPageNoteDetailState = {
  status: 'idle',
  note: null,
  error: null,
};

function learningPageNoteDetailReducer(
  state: LearningPageNoteDetailState,
  action: LearningPageNoteDetailAction,
): LearningPageNoteDetailState {
  switch (action.type) {
    case 'idle':
      return markLearningNotesIdle(state, { note: null });
    case 'loading':
      return markLearningNotesLoading(state);
    case 'loaded':
      return markLearningNotesReady(state, { note: action.note });
    case 'failed':
      return markLearningNotesFailed(state, action.message);
    default:
      return state;
  }
}

interface LearningNotesLoadFields {
  status: LoadStatus;
  error: string | null;
}

type LearningNotesLoadAction =
  | { type: 'idle' }
  | { type: 'loading' }
  | { type: 'failed'; message: string };

type LearningNotesLoadedAction = { type: 'loaded' };

type RequestTokenRef = { current: number };

function markLearningNotesIdle<TState extends LearningNotesLoadFields>(
  state: TState,
  reset: Partial<TState>,
): TState {
  return {
    ...state,
    ...reset,
    status: 'idle',
    error: null,
  };
}

function markLearningNotesLoading<TState extends LearningNotesLoadFields>(
  state: TState,
): TState {
  return {
    ...state,
    status: 'loading',
    error: null,
  };
}

function markLearningNotesReady<TState extends LearningNotesLoadFields>(
  state: TState,
  patch: Partial<TState>,
): TState {
  return {
    ...state,
    ...patch,
    status: 'ready',
    error: null,
  };
}

function markLearningNotesFailed<TState extends LearningNotesLoadFields>(
  state: TState,
  message: string,
): TState {
  return {
    ...state,
    status: 'error',
    error: message,
  };
}

function refreshLearningNotesState<TState extends { reloadToken: number }>(
  state: TState,
): TState {
  return {
    ...state,
    reloadToken: state.reloadToken + 1,
  };
}

function runLearningNotesLoad<TLoadedAction extends LearningNotesLoadedAction>({
  dispatch,
  fallbackErrorKey,
  load,
  requestTokenRef,
}: {
  dispatch: (action: LearningNotesLoadAction | TLoadedAction) => void;
  fallbackErrorKey: string;
  load: (signal: AbortSignal) => Promise<TLoadedAction>;
  requestTokenRef: RequestTokenRef;
}): () => void {
  const requestToken = ++requestTokenRef.current;
  const controller = new AbortController();
  dispatch({ type: 'loading' });
  load(controller.signal)
    .then((action) => {
      if (
        !isActiveLearningNotesRequest(controller, requestToken, requestTokenRef)
      )
        return;
      dispatch(action);
    })
    .catch((caught: unknown) => {
      if (
        !isActiveLearningNotesRequest(controller, requestToken, requestTokenRef)
      )
        return;
      dispatch({
        type: 'failed',
        message: resolveLearningNotesError(caught, fallbackErrorKey),
      });
    });
  return () => controller.abort();
}

function isActiveLearningNotesRequest(
  controller: AbortController,
  requestToken: number,
  requestTokenRef: RequestTokenRef,
): boolean {
  return !controller.signal.aborted && requestToken === requestTokenRef.current;
}

function resolveLearningNotesError(
  caught: unknown,
  fallbackKey: string,
): string {
  return caught instanceof LearningNotesApiError
    ? caught.message
    : i18n.t(fallbackKey);
}

export interface UseLearningPageNotesListResult {
  status: LoadStatus;
  items: LearningPageNoteListItem[];
  myNote: LearningPageNoteListItem | null;
  othersNotes: LearningPageNoteListItem[];
  error: string | null;
  refresh: () => void;
}

export function useLearningPageNotesList(
  token: string | null,
  courseSlug: string | null,
  lessonId: string | null,
): UseLearningPageNotesListResult {
  const [{ status, items, error, reloadToken }, dispatch] = useReducer(
    learningPageNotesListReducer,
    INITIAL_LEARNING_PAGE_NOTES_LIST_STATE,
  );
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!token || !courseSlug || !lessonId) {
      dispatch({ type: 'idle' });
      return;
    }
    return runLearningNotesLoad<LearningPageNotesListLoadedAction>({
      dispatch,
      fallbackErrorKey: 'apps:learning.errors.listNotesFailed',
      requestTokenRef,
      load: (signal) =>
        listLearningPageNotes(token, courseSlug, lessonId, { signal }).then(
          (response) => ({
            type: 'loaded',
            items: response.items,
          }),
        ),
    });
  }, [token, courseSlug, lessonId, reloadToken]);

  const refresh = useCallback(() => dispatch({ type: 'refresh' }), []);

  const myNote = items.find((item) => item.is_mine) ?? null;
  const othersNotes = items.filter((item) => !item.is_mine);

  return { status, items, myNote, othersNotes, error, refresh };
}

export interface UseMyLearningPageNoteResult {
  status: LoadStatus;
  note: LearningPageNoteDetail | null;
  error: string | null;
  saving: boolean;
  refresh: () => void;
  upsert: (
    payload: LearningPageNoteUpsertPayload,
  ) => Promise<LearningPageNoteDetail>;
  archive: (docId: string) => Promise<LearningPageNoteDetail>;
  restore: (docId: string) => Promise<LearningPageNoteDetail>;
}

export function useMyLearningPageNote(
  token: string | null,
  courseSlug: string | null,
  lessonId: string | null,
): UseMyLearningPageNoteResult {
  const [{ status, note, error, saving, reloadToken }, dispatch] = useReducer(
    myLearningPageNoteReducer,
    INITIAL_MY_LEARNING_PAGE_NOTE_STATE,
  );
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!token || !courseSlug || !lessonId) {
      dispatch({ type: 'idle' });
      return;
    }
    return runLearningNotesLoad<LearningPageNoteLoadedAction>({
      dispatch,
      fallbackErrorKey: 'apps:learning.errors.loadMineFailed',
      requestTokenRef,
      load: (signal) =>
        fetchMyLearningPageNote(token, courseSlug, lessonId, { signal }).then(
          (response) => ({
            type: 'loaded',
            note: response,
          }),
        ),
    });
  }, [token, courseSlug, lessonId, reloadToken]);

  const refresh = useCallback(() => dispatch({ type: 'refresh' }), []);

  const upsert = useCallback(
    async (payload: LearningPageNoteUpsertPayload) => {
      if (!token)
        throw new LearningNotesApiError(
          401,
          i18n.t('auth:errors.noActiveSession'),
        );
      dispatch({ type: 'savingStarted' });
      try {
        const saved = await upsertMyLearningPageNote(token, payload);
        dispatch({ type: 'loaded', note: saved });
        return saved;
      } finally {
        dispatch({ type: 'savingFinished' });
      }
    },
    [token],
  );

  const archive = useCallback(
    async (docId: string) => {
      if (!token)
        throw new LearningNotesApiError(
          401,
          i18n.t('auth:errors.noActiveSession'),
        );
      dispatch({ type: 'savingStarted' });
      try {
        const archived = await archiveLearningPageNote(token, docId);
        dispatch({ type: 'loaded', note: null });
        return archived;
      } finally {
        dispatch({ type: 'savingFinished' });
      }
    },
    [token],
  );

  const restore = useCallback(
    async (docId: string) => {
      if (!token)
        throw new LearningNotesApiError(
          401,
          i18n.t('auth:errors.noActiveSession'),
        );
      dispatch({ type: 'savingStarted' });
      try {
        const restored = await restoreLearningPageNote(token, docId);
        dispatch({ type: 'loaded', note: restored });
        return restored;
      } finally {
        dispatch({ type: 'savingFinished' });
      }
    },
    [token],
  );

  return { status, note, error, saving, refresh, upsert, archive, restore };
}

export interface UseLearningPageNoteDetailResult {
  status: LoadStatus;
  note: LearningPageNoteDetail | null;
  error: string | null;
}

/** Lazy-load the full body of a note when a card is expanded. */
export function useLearningPageNoteDetail(
  token: string | null,
  docId: string | null,
): UseLearningPageNoteDetailResult {
  const [{ status, note, error }, dispatch] = useReducer(
    learningPageNoteDetailReducer,
    INITIAL_LEARNING_PAGE_NOTE_DETAIL_STATE,
  );
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!token || !docId) {
      dispatch({ type: 'idle' });
      return;
    }
    return runLearningNotesLoad<LearningPageNoteLoadedAction>({
      dispatch,
      fallbackErrorKey: 'apps:learning.errors.loadNoteFailed',
      requestTokenRef,
      load: (signal) =>
        fetchLearningPageNoteDetail(token, docId, { signal }).then(
          (detail) => ({
            type: 'loaded',
            note: detail,
          }),
        ),
    });
  }, [token, docId]);

  return { status, note, error };
}
