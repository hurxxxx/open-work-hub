import { useCallback, useEffect, useState } from 'react';

const AI_SCOPE_STORAGE_PREFIX = 'open-alm.ai.scope.';

export function chatScopeStorageKey(
  workspaceSlug: string | undefined,
): string | null {
  if (!workspaceSlug) return null;
  return `${AI_SCOPE_STORAGE_PREFIX}${workspaceSlug}`;
}

export function readPersistedScope(
  workspaceSlug: string | undefined,
): string[] | null {
  const key = chatScopeStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed.filter((item): item is string => typeof item === 'string');
  } catch {
    return null;
  }
}

export function writePersistedScope(
  workspaceSlug: string | undefined,
  selection: string[] | null,
): void {
  const key = chatScopeStorageKey(workspaceSlug);
  if (!key || typeof window === 'undefined') return;
  try {
    if (selection === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, JSON.stringify(selection));
    }
  } catch {
    // Quota or disabled storage: picker still works in-memory for the session.
  }
}

type WorkspaceScopedAllowedAppIds = {
  workspaceSlug: string | undefined;
  allowedAppIds: string[] | null;
};

function readWorkspaceScopedAllowedAppIds(
  workspaceSlug: string | undefined,
): WorkspaceScopedAllowedAppIds {
  return {
    workspaceSlug,
    allowedAppIds: readPersistedScope(workspaceSlug),
  };
}

function resolveWorkspaceScopedAllowedAppIds(
  state: WorkspaceScopedAllowedAppIds,
  workspaceSlug: string | undefined,
): WorkspaceScopedAllowedAppIds {
  if (state.workspaceSlug === workspaceSlug) {
    return state;
  }

  return readWorkspaceScopedAllowedAppIds(workspaceSlug);
}

export function useWorkspaceScopedAllowedAppIds(
  workspaceSlug: string | undefined,
): [string[] | null, (nextAllowedAppIds: string[] | null) => void] {
  const [state, setState] = useState<WorkspaceScopedAllowedAppIds>(() =>
    readWorkspaceScopedAllowedAppIds(workspaceSlug),
  );
  const scopedAllowedAppIds = resolveWorkspaceScopedAllowedAppIds(
    state,
    workspaceSlug,
  );
  const allowedAppIds = scopedAllowedAppIds.allowedAppIds;

  useEffect(() => {
    if (state.workspaceSlug === workspaceSlug) {
      return;
    }

    setState((current) => {
      if (current.workspaceSlug === workspaceSlug) {
        return current;
      }

      return scopedAllowedAppIds;
    });
  }, [scopedAllowedAppIds, state.workspaceSlug, workspaceSlug]);

  const setAllowedAppIds = useCallback(
    (nextAllowedAppIds: string[] | null) => {
      setState({
        workspaceSlug,
        allowedAppIds: nextAllowedAppIds,
      });
    },
    [workspaceSlug],
  );

  useEffect(() => {
    writePersistedScope(workspaceSlug, allowedAppIds);
  }, [allowedAppIds, workspaceSlug]);

  return [allowedAppIds, setAllowedAppIds];
}
