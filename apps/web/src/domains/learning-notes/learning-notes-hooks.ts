import { useCallback, useEffect, useRef, useState } from 'react';

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
  const [status, setStatus] = useState<LoadStatus>('idle');
  const [items, setItems] = useState<LearningPageNoteListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!token || !courseSlug || !lessonId) {
      setStatus('idle');
      setItems([]);
      setError(null);
      return;
    }
    const requestToken = ++requestTokenRef.current;
    const controller = new AbortController();
    setStatus('loading');
    setError(null);
    (async () => {
      try {
        const response = await listLearningPageNotes(token, courseSlug, lessonId, {
          signal: controller.signal,
        });
        if (requestToken !== requestTokenRef.current) return;
        setItems(response.items);
        setStatus('ready');
      } catch (caught) {
        if (controller.signal.aborted) return;
        if (requestToken !== requestTokenRef.current) return;
        setError(
          caught instanceof LearningNotesApiError
            ? caught.message
            : '노트 목록을 불러오지 못했습니다.',
        );
        setStatus('error');
      }
    })();
    return () => controller.abort();
  }, [token, courseSlug, lessonId, reloadToken]);

  const refresh = useCallback(() => setReloadToken((v) => v + 1), []);

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
  const [status, setStatus] = useState<LoadStatus>('idle');
  const [note, setNote] = useState<LearningPageNoteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!token || !courseSlug || !lessonId) {
      setStatus('idle');
      setNote(null);
      setError(null);
      return;
    }
    const requestToken = ++requestTokenRef.current;
    const controller = new AbortController();
    setStatus('loading');
    setError(null);
    (async () => {
      try {
        const response = await fetchMyLearningPageNote(token, courseSlug, lessonId, {
          signal: controller.signal,
        });
        if (requestToken !== requestTokenRef.current) return;
        setNote(response);
        setStatus('ready');
      } catch (caught) {
        if (controller.signal.aborted) return;
        if (requestToken !== requestTokenRef.current) return;
        setError(
          caught instanceof LearningNotesApiError
            ? caught.message
            : '내 노트를 불러오지 못했습니다.',
        );
        setStatus('error');
      }
    })();
    return () => controller.abort();
  }, [token, courseSlug, lessonId, reloadToken]);

  const refresh = useCallback(() => setReloadToken((v) => v + 1), []);

  const upsert = useCallback(
    async (payload: LearningPageNoteUpsertPayload) => {
      if (!token) throw new LearningNotesApiError(401, '로그인이 필요합니다.');
      setSaving(true);
      try {
        const saved = await upsertMyLearningPageNote(token, payload);
        setNote(saved);
        setStatus('ready');
        return saved;
      } finally {
        setSaving(false);
      }
    },
    [token],
  );

  const archive = useCallback(
    async (docId: string) => {
      if (!token) throw new LearningNotesApiError(401, '로그인이 필요합니다.');
      setSaving(true);
      try {
        const archived = await archiveLearningPageNote(token, docId);
        setNote(null);
        return archived;
      } finally {
        setSaving(false);
      }
    },
    [token],
  );

  const restore = useCallback(
    async (docId: string) => {
      if (!token) throw new LearningNotesApiError(401, '로그인이 필요합니다.');
      setSaving(true);
      try {
        const restored = await restoreLearningPageNote(token, docId);
        setNote(restored);
        return restored;
      } finally {
        setSaving(false);
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
  const [status, setStatus] = useState<LoadStatus>('idle');
  const [note, setNote] = useState<LearningPageNoteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !docId) {
      setStatus('idle');
      setNote(null);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setStatus('loading');
    setError(null);
    (async () => {
      try {
        const detail = await fetchLearningPageNoteDetail(token, docId, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setNote(detail);
        setStatus('ready');
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(
          caught instanceof LearningNotesApiError
            ? caught.message
            : '노트를 불러오지 못했습니다.',
        );
        setStatus('error');
      }
    })();
    return () => controller.abort();
  }, [token, docId]);

  return { status, note, error };
}
