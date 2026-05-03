import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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

export function useWizardState({
  workspaceSlug,
  generationId,
  onIdChange,
}: UseWizardStateOpts): WizardStateApi {
  const { token } = useAuth();
  const [row, setRow] = useState<ImageGeneration | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(generationId));
  const [error, setError] = useState<string | null>(null);
  const [autosave, setAutosave] = useState<AutosaveState>('idle');

  const pendingPatch = useRef<ImageGenerationPatchPayload>({});
  const pendingCreate = useRef<ImageGenerationCreatePayload | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inflight = useRef<Promise<void> | null>(null);
  const rowRef = useRef<ImageGeneration | null>(null);

  rowRef.current = row;

  // Initial / id-change load.
  useEffect(() => {
    if (!token) return;
    if (!generationId) {
      setRow(null);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getImageGeneration(token, workspaceSlug, generationId)
      .then((fetched) => {
        if (cancelled) return;
        setRow(fetched);
        setError(null);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token, workspaceSlug, generationId]);

  const flushNow = useCallback(async () => {
    if (!token) return;
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
      debounceTimer.current = null;
    }
    if (inflight.current) {
      await inflight.current;
    }
    const create = pendingCreate.current;
    const patch = pendingPatch.current;
    pendingPatch.current = {};
    pendingCreate.current = null;
    if (!create && Object.keys(patch).length === 0) return;

    setAutosave('saving');
    const work = (async () => {
      try {
        let workingRow = rowRef.current;
        if (!workingRow) {
          const initial: ImageGenerationCreatePayload = { ...(create ?? {}), ...patch };
          workingRow = await createImageGeneration(token, workspaceSlug, initial);
          rowRef.current = workingRow;
          setRow(workingRow);
          onIdChange(workingRow.id);
        } else if (Object.keys(patch).length > 0) {
          const updated = await patchImageGeneration(token, workspaceSlug, workingRow.id, patch);
          rowRef.current = updated;
          setRow(updated);
        }
        setAutosave('saved');
        setError(null);
      } catch (err) {
        setAutosave('error');
        setError(err instanceof Error ? err.message : i18n.t('apps:ai.imageWizard.errors.saveFailed'));
      } finally {
        inflight.current = null;
      }
    })();
    inflight.current = work;
    await work;
  }, [token, workspaceSlug, onIdChange]);

  const schedule = useCallback(() => {
    setAutosave('pending');
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      void flushNow();
    }, PATCH_DEBOUNCE_MS);
  }, [flushNow]);

  const update = useCallback<WizardStateApi['update']>(
    (patch, options) => {
      pendingPatch.current = { ...pendingPatch.current, ...patch };
      if (options?.initialCreate) {
        pendingCreate.current = { ...(pendingCreate.current ?? {}), ...options.initialCreate };
      }
      // Optimistically reflect in local state if row exists.
      setRow((prev) => {
        if (!prev) return prev;
        const merged: ImageGeneration = { ...prev };
        for (const key of Object.keys(patch) as (keyof ImageGenerationPatchPayload)[]) {
          const value = patch[key];
          if (value !== undefined) {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (merged as any)[key] = value;
          }
        }
        return merged;
      });
      schedule();
    },
    [schedule],
  );

  const applyServer = useCallback((next: ImageGeneration) => {
    rowRef.current = next;
    setRow(next);
  }, []);

  const startNew = useCallback<WizardStateApi['startNew']>(
    async (payload) => {
      if (!token) throw new Error(i18n.t('auth:errors.noActiveSession'));
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
        debounceTimer.current = null;
      }
      pendingPatch.current = {};
      pendingCreate.current = null;
      setAutosave('saving');
      try {
        const created = await createImageGeneration(token, workspaceSlug, payload);
        rowRef.current = created;
        setRow(created);
        onIdChange(created.id);
        setAutosave('saved');
        setError(null);
        return created;
      } catch (err) {
        setAutosave('error');
        const message =
          err instanceof Error ? err.message : i18n.t('apps:ai.imageWizard.errors.startFailed');
        setError(message);
        throw err;
      }
    },
    [token, workspaceSlug, onIdChange],
  );

  // Unmount: flush pending.
  useEffect(() => {
    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, []);

  return useMemo(
    () => ({
      row,
      loading,
      error,
      autosave,
      update,
      flush: flushNow,
      applyServer,
      startNew,
    }),
    [row, loading, error, autosave, update, flushNow, applyServer, startNew],
  );
}
