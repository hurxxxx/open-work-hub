export type CoreBackgroundWorkStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export type CoreBackgroundWorkTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export interface CoreBackgroundWorkItem {
  id: string;
  sourceId: string;
  kind: string;
  title: string;
  description?: string;
  status: CoreBackgroundWorkStatus;
  href?: string;
  cancellable?: boolean;
  updatedAt: string;
}

export interface CoreBackgroundWorkRuntimeSource {
  /** Owning workspace app. The source is inactive when this app is disabled. */
  appId: string;
  id: string;
  /** Poll cadence while at least one item is queued or running. */
  pollIntervalMs?: number;
  /** Poll cadence after the initial check when no active item is known. */
  idlePollIntervalMs?: number;
  /** Required workspace nav item for feature-level enablement. */
  requiredNavItemId?: string;
  list: (context: {
    token: string;
    workspaceSlug: string;
    t: CoreBackgroundWorkTranslator;
  }) => Promise<CoreBackgroundWorkItem[]>;
  cancel?: (context: {
    token: string;
    workspaceSlug: string;
    item: CoreBackgroundWorkItem;
  }) => Promise<void>;
}

export type CoreBackgroundWorkToastEvent =
  | { type: 'completed'; item: CoreBackgroundWorkItem }
  | { type: 'failed'; item: CoreBackgroundWorkItem }
  | { type: 'cancelled'; item: CoreBackgroundWorkItem };

export interface CoreBackgroundWorkCadence {
  activePollIntervalMs: number;
  idlePollIntervalMs: number;
}

export interface CoreBackgroundWorkSessionSnapshot {
  items: CoreBackgroundWorkItem[];
  activeItems: CoreBackgroundWorkItem[];
  nextStatuses: Map<string, CoreBackgroundWorkStatus>;
  toastEvents: CoreBackgroundWorkToastEvent[];
  nextPollDelayMs: number;
}

export interface CoreBackgroundWorkSourceItemsSnapshot {
  items: CoreBackgroundWorkItem[];
  itemsBySource: Map<string, CoreBackgroundWorkItem[]>;
}

const DEFAULT_ACTIVE_POLL_INTERVAL_MS = 5000;
const DEFAULT_IDLE_POLL_INTERVAL_MS = 30000;

export function isActiveCoreBackgroundWorkStatus(
  status: CoreBackgroundWorkStatus,
): boolean {
  return status === 'queued' || status === 'running';
}

export function coreBackgroundWorkItemKey(
  item: CoreBackgroundWorkItem,
): string {
  return `${item.sourceId}:${item.id}`;
}

export function resolveCoreBackgroundWorkCadence(
  sources: readonly Pick<
    CoreBackgroundWorkRuntimeSource,
    'pollIntervalMs' | 'idlePollIntervalMs'
  >[],
): CoreBackgroundWorkCadence {
  if (sources.length === 0) {
    return {
      activePollIntervalMs: DEFAULT_ACTIVE_POLL_INTERVAL_MS,
      idlePollIntervalMs: DEFAULT_IDLE_POLL_INTERVAL_MS,
    };
  }
  return {
    activePollIntervalMs: Math.min(
      ...sources.map(
        (source) => source.pollIntervalMs ?? DEFAULT_ACTIVE_POLL_INTERVAL_MS,
      ),
    ),
    idlePollIntervalMs: Math.min(
      ...sources.map(
        (source) => source.idlePollIntervalMs ?? DEFAULT_IDLE_POLL_INTERVAL_MS,
      ),
    ),
  };
}

export function selectActiveCoreBackgroundWorkItems(
  items: CoreBackgroundWorkItem[],
): CoreBackgroundWorkItem[] {
  return items
    .filter((item) => isActiveCoreBackgroundWorkStatus(item.status))
    .sort(
      (left, right) =>
        new Date(right.updatedAt).getTime() -
        new Date(left.updatedAt).getTime(),
    );
}

export function filterCoreBackgroundWorkSourcesForWorkspace(
  sources: readonly CoreBackgroundWorkRuntimeSource[],
  {
    enabledAppIds,
    enabledNavItemIds,
  }: {
    enabledAppIds: Iterable<string>;
    enabledNavItemIds: Iterable<string>;
  },
): CoreBackgroundWorkRuntimeSource[] {
  const enabledApps = new Set(enabledAppIds);
  const enabledNavItems = new Set(enabledNavItemIds);
  return sources.filter((source) => {
    if (!enabledApps.has(source.appId)) {
      return false;
    }
    if (
      source.requiredNavItemId &&
      !enabledNavItems.has(source.requiredNavItemId)
    ) {
      return false;
    }
    return true;
  });
}

export function mergeCoreBackgroundWorkSourceListResults({
  previousItemsBySource,
  settled,
  sources,
}: {
  previousItemsBySource: ReadonlyMap<string, readonly CoreBackgroundWorkItem[]>;
  settled: readonly PromiseSettledResult<CoreBackgroundWorkItem[]>[];
  sources: readonly Pick<CoreBackgroundWorkRuntimeSource, 'id'>[];
}): CoreBackgroundWorkSourceItemsSnapshot {
  const itemsBySource = new Map<string, CoreBackgroundWorkItem[]>();
  for (const [index, source] of sources.entries()) {
    const result = settled[index];
    if (result?.status === 'fulfilled') {
      itemsBySource.set(source.id, result.value);
      continue;
    }
    const previousItems = previousItemsBySource.get(source.id);
    if (previousItems) {
      itemsBySource.set(source.id, [...previousItems]);
    }
  }
  return {
    items: sources.flatMap((source) => itemsBySource.get(source.id) ?? []),
    itemsBySource,
  };
}

export function buildCoreBackgroundWorkSessionSnapshot({
  items,
  previousStatuses,
  cadence,
}: {
  items: CoreBackgroundWorkItem[];
  previousStatuses: ReadonlyMap<string, CoreBackgroundWorkStatus>;
  cadence: CoreBackgroundWorkCadence;
}): CoreBackgroundWorkSessionSnapshot {
  const nextStatuses = new Map<string, CoreBackgroundWorkStatus>();
  const toastEvents: CoreBackgroundWorkToastEvent[] = [];

  for (const item of items) {
    const key = coreBackgroundWorkItemKey(item);
    const previous = previousStatuses.get(key);
    if (
      previous &&
      isActiveCoreBackgroundWorkStatus(previous) &&
      !isActiveCoreBackgroundWorkStatus(item.status)
    ) {
      if (item.status === 'succeeded') {
        toastEvents.push({ type: 'completed', item });
      } else if (item.status === 'failed') {
        toastEvents.push({ type: 'failed', item });
      } else if (item.status === 'cancelled') {
        toastEvents.push({ type: 'cancelled', item });
      }
    }
    nextStatuses.set(key, item.status);
  }

  const activeItems = selectActiveCoreBackgroundWorkItems(items);
  return {
    items,
    activeItems,
    nextStatuses,
    toastEvents,
    nextPollDelayMs:
      activeItems.length > 0
        ? cadence.activePollIntervalMs
        : cadence.idlePollIntervalMs,
  };
}

export function addCancellingCoreBackgroundWorkKey(
  current: ReadonlySet<string>,
  item: CoreBackgroundWorkItem,
): Set<string> {
  return new Set(current).add(coreBackgroundWorkItemKey(item));
}

export function removeCancellingCoreBackgroundWorkKey(
  current: ReadonlySet<string>,
  item: CoreBackgroundWorkItem,
): Set<string> {
  const next = new Set(current);
  next.delete(coreBackgroundWorkItemKey(item));
  return next;
}
