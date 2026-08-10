import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { i18n } from '@/src/platform/i18n';
import {
  createImageGeneration,
  getImageGeneration,
  patchImageGeneration,
  type ImageGeneration,
  type ImageGenerationCreatePayload,
  type ImageGenerationPatchPayload,
} from '../../api/image-wizard-api';

const PATCH_DEBOUNCE_MS = 500;

export type StepId = 1 | 2 | 3 | 4;

export type AutosaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

export interface WizardStateApi {
  row: ImageGeneration | null;
  loading: boolean;
  error: string | null;
  autosave: AutosaveState;
  /** Patch row (debounced autosave). Materializes row if it doesn't yet exist. */
  update: (patch: ImageGenerationPatchPayload, options?: { initialCreate?: ImageGenerationCreatePayload }) => void;
  /** Force-flush any pending patch immediately and await it. */
  flush: () => Promise<void>;
  /** Replace the local row state (used after server-driven changes). */
  applyServer: (next: ImageGeneration) => void;
  /** Recreate as a brand-new generation seeded from a payload (used by template pick / clone). */
  startNew: (payload: ImageGenerationCreatePayload) => Promise<ImageGeneration>;
}

interface UseWizardStateOpts {
  workspaceSlug: string;
  generationId: string | null;
  onIdChange: (newId: string) => void;
}

interface WizardLoadState {
  row: ImageGeneration | null;
  loading: boolean;
  error: string | null;
}

type WizardLoadAction =
  | { type: 'reset' }
  | { type: 'loading' }
  | { type: 'loaded'; row: ImageGeneration }
  | { type: 'loadFailed'; error: string }
  | { type: 'rowUpdated'; row: ImageGeneration }
  | { type: 'saveFailed'; error: string }
  | { type: 'errorCleared' };

function getInitialLoadState(generationId: string | null): WizardLoadState {
  return {
    row: null,
    loading: Boolean(generationId),
    error: null,
  };
}

function wizardLoadReducer(
  state: WizardLoadState,
  action: WizardLoadAction,
): WizardLoadState {
  switch (action.type) {
    case 'reset':
      return {
        row: null,
        loading: false,
        error: null,
      };
    case 'loading':
      return {
        ...state,
        loading: true,
      };
    case 'loaded':
      return {
        row: action.row,
        loading: false,
        error: null,
      };
    case 'loadFailed':
      return {
        ...state,
        loading: false,
        error: action.error,
      };
    case 'rowUpdated':
      return {
        ...state,
        row: action.row,
      };
    case 'saveFailed':
      return {
        ...state,
        error: action.error,
      };
    case 'errorCleared':
      return state.error ? { ...state, error: null } : state;
  }
}

function mergeDraftPayload(
  current: ImageGenerationCreatePayload,
  patch: ImageGenerationCreatePayload,
): ImageGenerationCreatePayload {
  return {
    ...current,
    ...patch,
    ...(patch.style !== undefined
      ? { style: { ...(current.style ?? {}), ...patch.style } }
      : {}),
    ...(patch.layout !== undefined
      ? { layout: { ...(current.layout ?? {}), ...patch.layout } }
      : {}),
    ...(patch.details !== undefined
      ? { details: { ...(current.details ?? {}), ...patch.details } }
      : {}),
  };
}

export function hasGenerationPatch(patch: ImageGenerationPatchPayload): boolean {
  return Object.keys(patch).length > 0;
}

export function mergeGenerationPatchPayload(
  current: ImageGenerationPatchPayload,
  patch: ImageGenerationPatchPayload,
): ImageGenerationPatchPayload {
  return mergeDraftPayload(current, patch);
}

export function mergeGenerationCreatePayload(
  current: ImageGenerationCreatePayload | null,
  patch: ImageGenerationCreatePayload,
): ImageGenerationCreatePayload {
  return mergeDraftPayload(current ?? {}, patch);
}

export function applyLocalPatch(
  current: ImageGeneration,
  patch: ImageGenerationPatchPayload,
): ImageGeneration {
  return {
    ...current,
    ...(patch.template_id !== undefined ? { template_id: patch.template_id } : {}),
    ...(patch.is_template !== undefined ? { is_template: patch.is_template } : {}),
    ...(patch.use_case !== undefined ? { use_case: patch.use_case } : {}),
    ...(patch.use_case_other !== undefined
      ? { use_case_other: patch.use_case_other }
      : {}),
    ...(patch.style !== undefined
      ? { style: { ...current.style, ...patch.style } }
      : {}),
    ...(patch.layout !== undefined
      ? { layout: { ...current.layout, ...patch.layout } }
      : {}),
    ...(patch.details !== undefined
      ? { details: { ...current.details, ...patch.details } }
      : {}),
    ...(patch.context_refs !== undefined
      ? { context_refs: patch.context_refs }
      : {}),
  };
}

export function useWizardState({
  workspaceSlug,
  generationId,
  onIdChange,
}: UseWizardStateOpts): WizardStateApi {
  const { token } = useAuth();
  const [loadState, dispatchLoadState] = useReducer(
    wizardLoadReducer,
    generationId,
    getInitialLoadState,
  );
  const [autosave, setAutosave] = useState<AutosaveState>('idle');

  const pendingPatch = useRef<ImageGenerationPatchPayload>({});
  const pendingCreate = useRef<ImageGenerationCreatePayload | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflight = useRef<Promise<void> | null>(null);
  const rowRef = useRef<ImageGeneration | null>(null);

  rowRef.current = loadState.row;

  // Initial / id-change load.
  useEffect(() => {
    if (!token) return;
    if (!generationId) {
      dispatchLoadState({ type: 'reset' });
      return;
    }
    let cancelled = false;
    dispatchLoadState({ type: 'loading' });
    getImageGeneration(token, workspaceSlug, generationId)
      .then((fetched) => {
        if (cancelled) return;
        dispatchLoadState({ type: 'loaded', row: fetched });
      })
      .catch((err: Error) => {
        if (cancelled) return;
        dispatchLoadState({ type: 'loadFailed', error: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, generationId]);

  const clearDebounceTimer = useCallback(() => {
    const timer = debounceTimer.current;
    if (timer) {
      clearTimeout(timer);
      debounceTimer.current = null;
    }
  }, []);

  const flushNow = useCallback(async () => {
    if (!token) return;
    clearDebounceTimer();
    if (inflight.current) {
      await inflight.current;
    }
    const create = pendingCreate.current;
    const patch = pendingPatch.current;
    pendingPatch.current = {};
    pendingCreate.current = null;
    if (!create && !hasGenerationPatch(patch)) return;

    setAutosave('saving');
    const work = (async () => {
      try {
        let workingRow = rowRef.current;
        if (!workingRow) {
          const initial = mergeGenerationCreatePayload(create, patch);
          workingRow = await createImageGeneration(token, workspaceSlug, initial);
          rowRef.current = workingRow;
          dispatchLoadState({ type: 'rowUpdated', row: workingRow });
          onIdChange(workingRow.id);
        } else if (hasGenerationPatch(patch)) {
          const updated = await patchImageGeneration(token, workspaceSlug, workingRow.id, patch);
          rowRef.current = updated;
          dispatchLoadState({ type: 'rowUpdated', row: updated });
        }
        setAutosave('saved');
        dispatchLoadState({ type: 'errorCleared' });
      } catch (err) {
        setAutosave('error');
        dispatchLoadState({
          type: 'saveFailed',
          error: err instanceof Error
            ? err.message
            : i18n.t('apps:ai.imageWizard.errors.saveFailed'),
        });
      } finally {
        inflight.current = null;
      }
    })();
    inflight.current = work;
    await work;
  }, [clearDebounceTimer, token, workspaceSlug, onIdChange]);

  const schedule = useCallback(() => {
    setAutosave('pending');
    clearDebounceTimer();
    debounceTimer.current = setTimeout(() => {
      void flushNow();
    }, PATCH_DEBOUNCE_MS);
  }, [clearDebounceTimer, flushNow]);

  const update = useCallback<WizardStateApi['update']>(
    (patch, options) => {
      pendingPatch.current = mergeGenerationPatchPayload(pendingPatch.current, patch);
      if (options?.initialCreate) {
        pendingCreate.current = mergeGenerationCreatePayload(
          pendingCreate.current,
          options.initialCreate,
        );
      }
      // Optimistically reflect in local state if row exists.
      const currentRow = rowRef.current;
      if (currentRow) {
        const nextRow = applyLocalPatch(currentRow, patch);
        rowRef.current = nextRow;
        dispatchLoadState({ type: 'rowUpdated', row: nextRow });
      }
      schedule();
    },
    [schedule],
  );

  const applyServer = useCallback((next: ImageGeneration) => {
    rowRef.current = next;
    dispatchLoadState({ type: 'rowUpdated', row: next });
  }, []);

  const startNew = useCallback<WizardStateApi['startNew']>(
    async (payload) => {
      if (!token) throw new Error(i18n.t('auth:errors.noActiveSession'));
      clearDebounceTimer();
      pendingPatch.current = {};
      pendingCreate.current = null;
      setAutosave('saving');
      try {
        const created = await createImageGeneration(token, workspaceSlug, payload);
        rowRef.current = created;
        dispatchLoadState({ type: 'rowUpdated', row: created });
        onIdChange(created.id);
        setAutosave('saved');
        dispatchLoadState({ type: 'errorCleared' });
        return created;
      } catch (err) {
        setAutosave('error');
        const message =
          err instanceof Error ? err.message : i18n.t('apps:ai.imageWizard.errors.startFailed');
        dispatchLoadState({ type: 'saveFailed', error: message });
        throw err;
      }
    },
    [clearDebounceTimer, token, workspaceSlug, onIdChange],
  );

  // Unmount: flush pending.
  useEffect(() => {
    return clearDebounceTimer;
  }, [clearDebounceTimer]);

  return useMemo(
    () => ({
      row: loadState.row,
      loading: loadState.loading,
      error: loadState.error,
      autosave,
      update,
      flush: flushNow,
      applyServer,
      startNew,
    }),
    [loadState, autosave, update, flushNow, applyServer, startNew],
  );
}
