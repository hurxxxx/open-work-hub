export type DmThreadNavigationHistory = {
  back: string[];
  forward: string[];
};

export type DmThreadScrollSnapshot = {
  atBottom: boolean;
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
};

export type DmThreadScrollSnapshots = Record<string, DmThreadScrollSnapshot>;

export const DM_THREAD_SESSION_LIMIT = 30;
export const DM_THREAD_SCROLL_BOTTOM_THRESHOLD = 72;

export const DM_THREAD_NAVIGATION_INITIAL_STATE: DmThreadNavigationHistory = {
  back: [],
  forward: [],
};

export function selectDmThreadWithHistory(
  history: DmThreadNavigationHistory,
  input: {
    currentThreadId: string | null | undefined;
    nextThreadId: string | null | undefined;
    limit?: number;
  },
): DmThreadNavigationHistory {
  const currentThreadId = input.currentThreadId ?? null;
  const nextThreadId = input.nextThreadId ?? null;
  if (!currentThreadId || !nextThreadId || currentThreadId === nextThreadId) {
    return history;
  }
  return {
    back: [...history.back, currentThreadId].slice(
      -(input.limit ?? DM_THREAD_SESSION_LIMIT),
    ),
    forward: [],
  };
}

export function navigateDmThreadHistoryBack(
  history: DmThreadNavigationHistory,
  currentThreadId: string | null | undefined,
): {
  history: DmThreadNavigationHistory;
  threadId: string | null;
} {
  const nextThreadId = history.back.at(-1) ?? null;
  if (!nextThreadId) {
    return { history, threadId: null };
  }
  return {
    history: {
      back: history.back.slice(0, -1),
      forward: currentThreadId
        ? [currentThreadId, ...history.forward].slice(0, DM_THREAD_SESSION_LIMIT)
        : history.forward,
    },
    threadId: nextThreadId,
  };
}

export function navigateDmThreadHistoryForward(
  history: DmThreadNavigationHistory,
  currentThreadId: string | null | undefined,
): {
  history: DmThreadNavigationHistory;
  threadId: string | null;
} {
  const nextThreadId = history.forward[0] ?? null;
  if (!nextThreadId) {
    return { history, threadId: null };
  }
  return {
    history: {
      back: currentThreadId
        ? [...history.back, currentThreadId].slice(-DM_THREAD_SESSION_LIMIT)
        : history.back,
      forward: history.forward.slice(1),
    },
    threadId: nextThreadId,
  };
}

export function pruneDmThreadSessionIds(
  threadIds: readonly string[],
  validThreadIds: ReadonlySet<string>,
): string[] {
  return threadIds.filter((threadId) => validThreadIds.has(threadId));
}

export function pruneDmThreadNavigationHistory(
  history: DmThreadNavigationHistory,
  validThreadIds: ReadonlySet<string>,
): DmThreadNavigationHistory {
  return {
    back: pruneDmThreadSessionIds(history.back, validThreadIds),
    forward: pruneDmThreadSessionIds(history.forward, validThreadIds),
  };
}

export function isDmThreadScrolledToBottom(input: {
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
  threshold?: number;
}): boolean {
  return (
    input.scrollHeight - input.scrollTop - input.clientHeight <=
    (input.threshold ?? DM_THREAD_SCROLL_BOTTOM_THRESHOLD)
  );
}

export function dmThreadScrollSnapshot(input: {
  clientHeight: number;
  scrollHeight: number;
  scrollTop: number;
}): DmThreadScrollSnapshot {
  return {
    ...input,
    atBottom: isDmThreadScrolledToBottom(input),
  };
}

export function dmThreadBottomScrollSnapshot(input: {
  clientHeight: number;
  scrollHeight: number;
}): DmThreadScrollSnapshot {
  return {
    ...input,
    atBottom: true,
    scrollTop: input.scrollHeight,
  };
}

export function setDmThreadRecordValue<T>(
  record: Readonly<Record<string, T>>,
  threadId: string,
  value: T,
  limit = DM_THREAD_SESSION_LIMIT,
): Record<string, T> {
  const entries = Object.entries(record).filter(([key]) => key !== threadId);
  return Object.fromEntries([[threadId, value], ...entries].slice(0, limit));
}

export function omitDmThreadRecordValue<T>(
  record: Readonly<Record<string, T>>,
  threadId: string,
): Record<string, T> {
  const next: Record<string, T> = {};
  for (const [key, value] of Object.entries(record)) {
    if (key !== threadId) {
      next[key] = value;
    }
  }
  return next;
}

export function pruneDmThreadRecordValues<T>(
  record: Readonly<Record<string, T>>,
  validThreadIds: ReadonlySet<string>,
): Record<string, T> {
  const next: Record<string, T> = {};
  for (const [key, value] of Object.entries(record)) {
    if (validThreadIds.has(key)) {
      next[key] = value;
    }
  }
  return next;
}
