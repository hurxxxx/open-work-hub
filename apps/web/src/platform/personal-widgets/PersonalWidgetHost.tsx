import { Button } from '@open-work-hub/ui/primitives/button';
import { Input } from '@open-work-hub/ui/primitives/input';
import {
  Check,
  CheckCircle2,
  Circle,
  ClipboardList,
  FileText,
  ListTodo,
  Loader2,
  Maximize2,
  Minimize2,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from 'lucide-react';
import { LazyMotion, domAnimation, m } from 'motion/react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';

import {
  PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
  type PersonalTodoPmsTaskCreatedEventDetail,
} from './floating-panel-events';
import {
  DEFAULT_PERSONAL_WIDGET_PREFERENCES,
  countOpenTodos,
  parsePersonalWidgetPreferences,
  personalWidgetStorageKey,
  serializePersonalWidgetPreferences,
  sortPersonalTodos,
  type PersonalWidgetId,
  type PersonalWidgetMode,
  type PersonalWidgetPreferences,
} from './personal-widget-state';
import {
  createPersonalTodo,
  deletePersonalTodo,
  getPersonalMemo,
  listPersonalTodos,
  savePersonalMemo,
  updatePersonalTodo,
  type PersonalMemo,
  type PersonalTodoItem,
} from './personal-widgets-api';
type TodoMutation = 'create' | 'delete' | 'toggle';
type FloatingPanelSection = 'personal' | 'dockPanel';
type PersonalWidgetDockItemId = PersonalWidgetId | string;
type PersonalWidgetDockItem = {
  ariaLabel: string;
  badgeClassName?: string;
  badgeCount?: number;
  dirty?: boolean;
  id: PersonalWidgetDockItemId;
  label: string;
  renderIcon: (size: number) => ReactNode;
};

export interface PersonalWidgetSecondaryPanelAdapter {
  badgeClassName?: string;
  getLauncherLabel?: (unreadCount: number) => string;
  id: string;
  mountInBackgroundOnOpen?: boolean;
  onOpenEvent?: (event: Event) => void;
  onReload?: () => void;
  openEventName?: string;
  renderIcon: (size: number) => ReactNode;
  renderPanel: () => ReactNode;
  shouldActivateOnOpen?: (event: Event) => boolean;
  shortTitle: string;
  title: string;
  unreadCount?: number;
}

const EMPTY_DOCK_PANELS: readonly PersonalWidgetSecondaryPanelAdapter[] = [];

function readStoredPreferences(
  userId: string | null,
): PersonalWidgetPreferences {
  if (typeof window === 'undefined' || !userId) {
    return DEFAULT_PERSONAL_WIDGET_PREFERENCES;
  }
  return parsePersonalWidgetPreferences(
    window.localStorage.getItem(personalWidgetStorageKey(userId)),
  );
}

function writeStoredPreferences(
  userId: string | null,
  preferences: PersonalWidgetPreferences,
): void {
  if (typeof window === 'undefined' || !userId) {
    return;
  }
  window.localStorage.setItem(
    personalWidgetStorageKey(userId),
    serializePersonalWidgetPreferences(preferences),
  );
}

export function PersonalWidgetHost({
  dockPanels = EMPTY_DOCK_PANELS,
  onConvertTodoToPms,
  secondaryPanel,
}: {
  dockPanels?: readonly PersonalWidgetSecondaryPanelAdapter[];
  onConvertTodoToPms?: (todo: PersonalTodoItem) => void;
  secondaryPanel?: PersonalWidgetSecondaryPanelAdapter;
}) {
  const { token, user } = useAuth();
  const principalId = user?.id ?? null;
  const { t } = useTranslation('shell');
  const [preferences, setPreferences] = useState(() =>
    readStoredPreferences(principalId),
  );
  const [todos, setTodos] = useState<PersonalTodoItem[]>([]);
  const [memo, setMemo] = useState<PersonalMemo | null>(null);
  const [memoBody, setMemoBody] = useState('');
  const latestMemoBodyRef = useRef('');
  const [draftTitle, setDraftTitle] = useState('');
  const [editingTodoId, setEditingTodoId] = useState<string | null>(null);
  const [editingTodoTitle, setEditingTodoTitle] = useState('');
  const pendingTodoEditFocusIdRef = useRef<string | null>(null);
  const todoEditButtonRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [loading, setLoading] = useState(false);
  const [memoLoading, setMemoLoading] = useState(false);
  const [memoSaving, setMemoSaving] = useState(false);
  const [lastFailedMemoBody, setLastFailedMemoBody] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState<TodoMutation | null>(null);
  const [backgroundMountedDockPanelIds, setBackgroundMountedDockPanelIds] =
    useState<Set<string>>(() => new Set());
  const [mutatingTodoIds, setMutatingTodoIds] = useState<Set<string>>(
    () => new Set(),
  );
  const mode = preferences.mode;
  const activeWidget = preferences.activeWidget;
  const openTodoCount = useMemo(() => countOpenTodos(todos), [todos]);
  const externalDockPanels = useMemo<PersonalWidgetSecondaryPanelAdapter[]>(
    () => [...(secondaryPanel ? [secondaryPanel] : []), ...dockPanels],
    [dockPanels, secondaryPanel],
  );
  const activeDockPanel =
    externalDockPanels.find(
      (panel) => panel.id === preferences.activeDockPanelId,
    ) ?? null;
  const activePanelSection: FloatingPanelSection = activeDockPanel
    ? 'dockPanel'
    : 'personal';
  const memoDirty = memoBody !== (memo?.body ?? '');
  const activeWidgetTitle =
    activeWidget === 'memo'
      ? t('personalWidgets.memo.title')
      : t('personalWidgets.todo.title');
  const activePanelTitle =
    activePanelSection === 'dockPanel' && activeDockPanel
      ? activeDockPanel.title
      : activeWidgetTitle;
  const memoAutoSaveStatus = memoSaving
    ? t('personalWidgets.memo.saving')
    : memoDirty
      ? t('personalWidgets.memo.unsaved')
      : t('personalWidgets.memo.saved');
  const personalReloadBusy = activeWidget === 'memo' ? memoLoading : loading;
  const reloadBusy =
    activePanelSection === 'personal' ? personalReloadBusy : false;
  const activeDockItemId: PersonalWidgetDockItemId =
    activePanelSection === 'dockPanel' && activeDockPanel
      ? activeDockPanel.id
      : activeWidget;

  useEffect(() => {
    writeStoredPreferences(principalId, preferences);
  }, [preferences, principalId]);

  useEffect(() => {
    if (editingTodoId !== null || !pendingTodoEditFocusIdRef.current) {
      return;
    }
    const todoId = pendingTodoEditFocusIdRef.current;
    pendingTodoEditFocusIdRef.current = null;
    todoEditButtonRefs.current.get(todoId)?.focus();
  }, [editingTodoId]);

  useEffect(() => {
    const availablePanelIds = new Set(
      externalDockPanels.map((panel) => panel.id),
    );
    setBackgroundMountedDockPanelIds((current) => {
      const next = new Set(
        [...current].filter((panelId) => availablePanelIds.has(panelId)),
      );
      return next.size === current.size ? current : next;
    });
  }, [externalDockPanels]);

  useEffect(() => {
    latestMemoBodyRef.current = memoBody;
  }, [memoBody]);

  const setMode = useCallback((nextMode: PersonalWidgetMode) => {
    setPreferences((current) => ({ ...current, mode: nextMode }));
  }, []);

  const setActiveDockPanelId = useCallback((panelId: string) => {
    setPreferences((current) => ({ ...current, activeDockPanelId: panelId }));
  }, []);

  const showPersonalSection = useCallback((nextWidget?: PersonalWidgetId) => {
    setPreferences((current) => ({
      ...current,
      activeWidget: nextWidget ?? current.activeWidget,
      activeDockPanelId: undefined,
    }));
  }, []);

  const showDockPanel = useCallback(
    (panelId: string) => {
      if (!externalDockPanels.some((panel) => panel.id === panelId)) {
        return;
      }
      setActiveDockPanelId(panelId);
    },
    [externalDockPanels, setActiveDockPanelId],
  );

  const handleDockItemClick = useCallback(
    (itemId: PersonalWidgetDockItemId) => {
      if (mode !== 'collapsed' && activeDockItemId === itemId) {
        setMode('collapsed');
        return;
      }
      if (itemId === 'todo' || itemId === 'memo') {
        showPersonalSection(itemId);
      } else {
        showDockPanel(itemId);
      }
      setMode('panel');
    },
    [activeDockItemId, mode, setMode, showDockPanel, showPersonalSection],
  );

  useEffect(() => {
    const registrations = externalDockPanels
      .filter((panel) => panel.openEventName)
      .map((panel) => {
        const handlePanelOpen = (event: Event) => {
          panel.onOpenEvent?.(event);
          if (panel.shouldActivateOnOpen?.(event) === false) {
            if (panel.mountInBackgroundOnOpen) {
              setBackgroundMountedDockPanelIds((current) => {
                if (current.has(panel.id)) {
                  return current;
                }
                const next = new Set(current);
                next.add(panel.id);
                return next;
              });
            }
            return;
          }
          setActiveDockPanelId(panel.id);
          setMode('panel');
        };

        window.addEventListener(panel.openEventName as string, handlePanelOpen);
        return [panel.openEventName as string, handlePanelOpen] as const;
      });
    if (registrations.length === 0) {
      return undefined;
    }
    return () => {
      registrations.forEach(([eventName, handler]) => {
        window.removeEventListener(eventName, handler);
      });
    };
  }, [externalDockPanels, setActiveDockPanelId, setMode]);

  const reloadTodos = useCallback(async () => {
    if (!token) {
      setTodos([]);
      setError(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await listPersonalTodos(token);
      setTodos(sortPersonalTodos(response.items));
    } catch {
      setError(t('personalWidgets.errors.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t, token]);

  const reloadMemo = useCallback(async () => {
    if (!token) {
      setMemo(null);
      setMemoBody('');
      setLastFailedMemoBody(null);
      setError(null);
      setMemoLoading(false);
      return;
    }

    setMemoLoading(true);
    setError(null);
    try {
      const response = await getPersonalMemo(token);
      setMemo(response);
      setMemoBody(response.body);
      setLastFailedMemoBody(null);
    } catch {
      setError(t('personalWidgets.errors.memoLoadFailed'));
    } finally {
      setMemoLoading(false);
    }
  }, [t, token]);

  useEffect(() => {
    void reloadTodos();
    void reloadMemo();
  }, [reloadMemo, reloadTodos]);

  useEffect(() => {
    if (mode === 'collapsed') {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMode('collapsed');
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [mode, setMode]);

  const addTodo = useCallback(async () => {
    const title = draftTitle.trim();
    if (!token || !title) {
      return;
    }
    setMutating('create');
    setError(null);
    try {
      const created = await createPersonalTodo(token, title);
      setTodos((current) => sortPersonalTodos([...current, created]));
      setDraftTitle('');
    } catch {
      setError(t('personalWidgets.errors.createFailed'));
    } finally {
      setMutating(null);
    }
  }, [draftTitle, t, token]);

  const toggleTodo = useCallback(
    async (todo: PersonalTodoItem) => {
      if (!token) {
        return;
      }
      setMutating('toggle');
      setMutatingTodoIds((current) => new Set(current).add(todo.id));
      setError(null);
      try {
        const updated = await updatePersonalTodo(token, todo.id, {
          completed: !todo.completed,
        });
        setTodos((current) =>
          sortPersonalTodos(
            current.map((item) => (item.id === updated.id ? updated : item)),
          ),
        );
      } catch {
        setError(t('personalWidgets.errors.updateFailed'));
      } finally {
        setMutating(null);
        setMutatingTodoIds((current) => {
          const next = new Set(current);
          next.delete(todo.id);
          return next;
        });
      }
    },
    [t, token],
  );

  const startEditingTodo = useCallback((todo: PersonalTodoItem) => {
    setEditingTodoId(todo.id);
    setEditingTodoTitle(todo.title);
    setError(null);
  }, []);

  const cancelEditingTodo = useCallback(() => {
    setEditingTodoId((current) => {
      pendingTodoEditFocusIdRef.current = current;
      return null;
    });
    setEditingTodoTitle('');
  }, []);

  const saveTodoTitle = useCallback(
    async (todo: PersonalTodoItem) => {
      const title = editingTodoTitle.trim();
      if (!token || !title) {
        return;
      }
      if (title === todo.title) {
        cancelEditingTodo();
        return;
      }

      setMutatingTodoIds((current) => new Set(current).add(todo.id));
      setError(null);
      try {
        const updated = await updatePersonalTodo(token, todo.id, { title });
        setTodos((current) =>
          sortPersonalTodos(
            current.map((item) => (item.id === updated.id ? updated : item)),
          ),
        );
        cancelEditingTodo();
      } catch {
        setError(t('personalWidgets.errors.updateFailed'));
      } finally {
        setMutatingTodoIds((current) => {
          const next = new Set(current);
          next.delete(todo.id);
          return next;
        });
      }
    },
    [cancelEditingTodo, editingTodoTitle, t, token],
  );

  const removeTodo = useCallback(
    async (todo: PersonalTodoItem) => {
      if (!token) {
        return;
      }
      setMutating('delete');
      setMutatingTodoIds((current) => new Set(current).add(todo.id));
      setError(null);
      try {
        await deletePersonalTodo(token, todo.id);
        setTodos((current) => current.filter((item) => item.id !== todo.id));
      } catch {
        setError(t('personalWidgets.errors.deleteFailed'));
      } finally {
        setMutating(null);
        setMutatingTodoIds((current) => {
          const next = new Set(current);
          next.delete(todo.id);
          return next;
        });
      }
    },
    [t, token],
  );

  useEffect(() => {
    const handlePmsTaskCreated = (event: Event) => {
      const detail = (
        event as CustomEvent<PersonalTodoPmsTaskCreatedEventDetail>
      ).detail;
      const todoId = detail?.todoId;
      if (!todoId) {
        return;
      }
      const todo = todos.find((item) => item.id === todoId);
      if (!todo) {
        return;
      }
      if (window.confirm(t('personalWidgets.todo.deleteAfterPmsCreate'))) {
        void removeTodo(todo);
      }
    };

    window.addEventListener(
      PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
      handlePmsTaskCreated,
    );
    return () => {
      window.removeEventListener(
        PERSONAL_TODO_PMS_TASK_CREATED_EVENT,
        handlePmsTaskCreated,
      );
    };
  }, [removeTodo, t, todos]);

  const saveMemo = useCallback(
    async (body: string) => {
      if (!token) {
        return;
      }
      setMemoSaving(true);
      setError(null);
      try {
        const saved = await savePersonalMemo(token, body);
        setMemo(saved);
        setLastFailedMemoBody(null);
        if (latestMemoBodyRef.current === body) {
          setMemoBody(saved.body);
        }
      } catch {
        setLastFailedMemoBody(body);
        setError(t('personalWidgets.errors.memoSaveFailed'));
      } finally {
        setMemoSaving(false);
      }
    },
    [t, token],
  );

  useEffect(() => {
    if (
      !token ||
      memoLoading ||
      memoSaving ||
      !memoDirty ||
      lastFailedMemoBody === memoBody
    ) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void saveMemo(memoBody);
    }, 800);
    return () => window.clearTimeout(timeoutId);
  }, [
    lastFailedMemoBody,
    memoBody,
    memoDirty,
    memoLoading,
    memoSaving,
    saveMemo,
    token,
  ]);

  const updateMemoBody = useCallback((body: string) => {
    setMemoBody(body);
    setLastFailedMemoBody(null);
  }, []);

  const reloadPersonalWidget = useCallback(() => {
    if (activeWidget === 'memo') {
      void reloadMemo();
    } else {
      void reloadTodos();
    }
  }, [activeWidget, reloadMemo, reloadTodos]);

  const reloadActiveSection = useCallback(() => {
    if (activePanelSection === 'dockPanel' && activeDockPanel?.onReload) {
      activeDockPanel.onReload();
      return;
    }
    reloadPersonalWidget();
  }, [activeDockPanel, activePanelSection, reloadPersonalWidget]);

  const convertTodoToPms = useCallback(
    (todo: PersonalTodoItem) => {
      onConvertTodoToPms?.(todo);
    },
    [onConvertTodoToPms],
  );

  const dockItems: PersonalWidgetDockItem[] = [
    ...externalDockPanels.map((panel) => {
      const unreadCount = panel.unreadCount ?? 0;
      return {
        ariaLabel:
          unreadCount > 0
            ? (panel.getLauncherLabel?.(unreadCount) ?? panel.title)
            : panel.title,
        badgeClassName:
          panel.badgeClassName ?? 'bg-app-accent text-app-accent-fg',
        badgeCount: unreadCount,
        id: panel.id,
        label: panel.shortTitle,
        renderIcon: panel.renderIcon,
      };
    }),
    {
      ariaLabel: t('personalWidgets.todo.open'),
      badgeClassName:
        'bg-[var(--ui-color-danger-text)] text-[var(--ui-color-danger-bg)]',
      badgeCount: openTodoCount,
      id: 'todo' as const,
      label: t('personalWidgets.todo.shortTitle'),
      renderIcon: (size: number) => (
        <ListTodo aria-hidden="true" size={size} strokeWidth={2.1} />
      ),
    },
    {
      ariaLabel: t('personalWidgets.memo.open'),
      dirty: memoDirty,
      id: 'memo' as const,
      label: t('personalWidgets.memo.shortTitle'),
      renderIcon: (size: number) => (
        <FileText aria-hidden="true" size={size} strokeWidth={2.1} />
      ),
    },
  ];
  const panelControls = (
    <div className="flex shrink-0 items-center gap-1">
      <Button
        aria-label={t('personalWidgets.reload')}
        disabled={reloadBusy}
        onClick={reloadActiveSection}
        size="icon"
        title={t('personalWidgets.reload')}
        variant="ghost"
      >
        <RefreshCw
          aria-hidden="true"
          className={reloadBusy ? 'animate-spin' : undefined}
          size={15}
        />
      </Button>
      <Button
        aria-label={
          mode === 'fullscreen'
            ? t('personalWidgets.exitFullscreen')
            : t('personalWidgets.enterFullscreen')
        }
        onClick={() => setMode(mode === 'fullscreen' ? 'panel' : 'fullscreen')}
        size="icon"
        title={
          mode === 'fullscreen'
            ? t('personalWidgets.exitFullscreen')
            : t('personalWidgets.enterFullscreen')
        }
        variant="ghost"
      >
        {mode === 'fullscreen' ? (
          <Minimize2 aria-hidden="true" size={15} />
        ) : (
          <Maximize2 aria-hidden="true" size={15} />
        )}
      </Button>
      <Button
        aria-label={t('personalWidgets.close')}
        onClick={() => setMode('collapsed')}
        size="icon"
        title={t('personalWidgets.close')}
        variant="ghost"
      >
        <X aria-hidden="true" size={15} />
      </Button>
    </div>
  );
  const panelFrameClassName =
    mode === 'fullscreen'
      ? 'bottom-3 left-3 right-12 top-3 rounded-lg max-[640px]:bottom-0 max-[640px]:left-0 max-[640px]:right-10 max-[640px]:top-0 max-[640px]:rounded-none'
      : activePanelSection === 'dockPanel'
        ? 'right-12 top-1/2 h-[min(740px,calc(100vh-2rem))] w-[min(760px,calc(100vw-4.75rem))] -translate-y-1/2 rounded-lg max-[640px]:bottom-0 max-[640px]:left-0 max-[640px]:right-10 max-[640px]:top-auto max-[640px]:h-[min(82dvh,680px)] max-[640px]:w-auto max-[640px]:translate-y-0 max-[640px]:rounded-b-none max-[640px]:rounded-t-lg'
        : 'right-12 top-1/2 h-[min(740px,calc(100vh-2rem))] w-[min(440px,calc(100vw-4.75rem))] -translate-y-1/2 rounded-lg max-[640px]:bottom-0 max-[640px]:left-0 max-[640px]:right-10 max-[640px]:top-auto max-[640px]:h-[min(82dvh,680px)] max-[640px]:w-auto max-[640px]:translate-y-0 max-[640px]:rounded-b-none max-[640px]:rounded-t-lg';

  if (!token) {
    return null;
  }

  return (
    <LazyMotion features={domAnimation}>
      {mode !== 'collapsed' ? (
        <m.aside
          aria-label={t('personalWidgets.panelLabel')}
          initial={{ opacity: 0, x: mode === 'fullscreen' ? 0 : 32 }}
          animate={{ opacity: 1, x: 0 }}
          className={cn(
            'fixed z-[var(--ui-z-floating-panel)] flex flex-col overflow-hidden border border-app-border bg-app-bg text-app-ink shadow-2xl outline-none',
            panelFrameClassName,
          )}
        >
          <header className="flex shrink-0 items-center justify-between gap-3 border-b border-app-border px-4 py-3">
            <div className="min-w-0">
              <p className="app-text-micro text-app-ink/45">
                {t('personalWidgets.eyebrow')}
              </p>
              <h2 className="app-text-title-md truncate text-app-ink">
                {activePanelTitle}
              </h2>
            </div>
            {panelControls}
          </header>

          <div className="flex min-h-0 min-w-0 w-full flex-1 overflow-x-hidden">
            {activePanelSection === 'dockPanel' && activeDockPanel ? (
              <section className="min-h-0 min-w-0 w-full flex-1 overflow-hidden">
                {activeDockPanel.renderPanel()}
              </section>
            ) : (
              <section className="flex min-h-0 min-w-0 w-full flex-1 flex-col overflow-hidden">
                <div className="grid shrink-0 gap-3 border-b border-app-border px-4 py-3">
                  <div className="flex items-center gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="app-text-caption text-app-ink/55">
                        {activeWidget === 'memo'
                          ? t('personalWidgets.memo.summary')
                          : t('personalWidgets.todo.summary', {
                              completed: todos.length - openTodoCount,
                              open: openTodoCount,
                            })}
                      </p>
                    </div>
                    {activeWidget === 'todo' ? (
                      <span className="app-text-micro shrink-0 rounded-full bg-app-surface px-2 py-1 text-app-ink/55">
                        {openTodoCount}
                      </span>
                    ) : memoDirty ? (
                      <span className="app-text-micro shrink-0 rounded-full bg-app-surface px-2 py-1 text-app-ink/55">
                        {memoAutoSaveStatus}
                      </span>
                    ) : null}
                  </div>
                </div>

                {activeWidget === 'todo' ? (
                  <form
                    className="flex shrink-0 gap-2 border-b border-app-border px-4 py-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void addTodo();
                    }}
                  >
                    <Input
                      aria-label={t('personalWidgets.todo.inputLabel')}
                      disabled={mutating === 'create'}
                      maxLength={240}
                      placeholder={t('personalWidgets.todo.inputPlaceholder')}
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                    />
                    <Button
                      aria-label={t('personalWidgets.todo.add')}
                      disabled={
                        mutating === 'create' || draftTitle.trim().length === 0
                      }
                      size="icon"
                      type="submit"
                      variant="primary"
                    >
                      {mutating === 'create' ? (
                        <Loader2
                          aria-hidden="true"
                          className="animate-spin"
                          size={15}
                        />
                      ) : (
                        <Plus aria-hidden="true" size={16} />
                      )}
                    </Button>
                  </form>
                ) : null}

                {error ? (
                  <div
                    className="mx-4 mt-3 rounded-md border border-[var(--ui-color-danger)]/35 bg-[var(--ui-color-danger)]/8 px-3 py-2"
                    role="alert"
                  >
                    <p className="app-text-caption text-[var(--ui-color-danger)]">
                      {error}
                    </p>
                  </div>
                ) : null}

                <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
                  {activeWidget === 'memo' ? (
                    <div className="flex h-full flex-col gap-3 p-4">
                      {memoLoading ? (
                        <div className="flex h-full items-center justify-center text-app-ink/40">
                          <Loader2
                            aria-hidden="true"
                            className="animate-spin"
                            size={20}
                          />
                        </div>
                      ) : (
                        <>
                          <textarea
                            aria-label={t('personalWidgets.memo.inputLabel')}
                            className="custom-scrollbar min-h-[260px] flex-1 resize-none rounded-md border border-app-border bg-app-surface px-3 py-2 text-[0.86rem] leading-6 text-app-ink outline-none transition-colors placeholder:text-app-ink/35 focus:border-app-accent focus:ring-2 focus:ring-app-accent/20"
                            maxLength={20000}
                            placeholder={t(
                              'personalWidgets.memo.inputPlaceholder',
                            )}
                            value={memoBody}
                            onChange={(event) =>
                              updateMemoBody(event.target.value)
                            }
                          />
                          <div className="flex shrink-0 items-center justify-between gap-3">
                            <span className="app-text-caption text-app-ink/45">
                              {t('personalWidgets.memo.characterCount', {
                                count: memoBody.length,
                              })}
                            </span>
                            <span
                              className={cn(
                                'app-text-caption inline-flex items-center gap-1.5 text-app-ink/55',
                                memoSaving && 'text-app-accent',
                                memoDirty &&
                                  !memoSaving &&
                                  'text-[var(--ui-color-warning)]',
                              )}
                            >
                              {memoSaving ? (
                                <Loader2
                                  aria-hidden="true"
                                  className="animate-spin"
                                  size={15}
                                />
                              ) : memoDirty ? (
                                <Circle aria-hidden="true" size={14} />
                              ) : (
                                <CheckCircle2 aria-hidden="true" size={14} />
                              )}
                              <span>{memoAutoSaveStatus}</span>
                            </span>
                          </div>
                        </>
                      )}
                    </div>
                  ) : loading && todos.length === 0 ? (
                    <div className="flex h-full items-center justify-center text-app-ink/40">
                      <Loader2
                        aria-hidden="true"
                        className="animate-spin"
                        size={20}
                      />
                    </div>
                  ) : todos.length === 0 ? (
                    <div className="flex h-full items-center justify-center px-8 text-center">
                      <p className="app-text-body-sm text-app-ink/45">
                        {t('personalWidgets.todo.empty')}
                      </p>
                    </div>
                  ) : (
                    <ul className="divide-y divide-app-border">
                      {todos.map((todo) => {
                        const busy = mutatingTodoIds.has(todo.id);
                        const editing = editingTodoId === todo.id;
                        return (
                          <li
                            key={todo.id}
                            className="flex items-start gap-2 px-4 py-3"
                          >
                            <button
                              type="button"
                              aria-label={t('personalWidgets.todo.toggle', {
                                title: todo.title,
                              })}
                              className="mt-0.5 shrink-0 rounded-md p-1 text-app-ink/45 transition-colors hover:bg-app-surface-hover hover:text-app-accent disabled:opacity-50"
                              disabled={busy || editing}
                              onClick={() => void toggleTodo(todo)}
                            >
                              {busy && mutating === 'toggle' ? (
                                <Loader2
                                  aria-hidden="true"
                                  className="animate-spin"
                                  size={17}
                                />
                              ) : todo.completed ? (
                                <CheckCircle2
                                  aria-hidden="true"
                                  className="text-app-accent"
                                  size={17}
                                />
                              ) : (
                                <Circle aria-hidden="true" size={17} />
                              )}
                            </button>
                            {editing ? (
                              <form
                                className="flex min-w-0 flex-1 items-center gap-1"
                                onSubmit={(event) => {
                                  event.preventDefault();
                                  void saveTodoTitle(todo);
                                }}
                              >
                                <Input
                                  autoFocus
                                  aria-label={t(
                                    'personalWidgets.todo.editInputLabel',
                                    { title: todo.title },
                                  )}
                                  disabled={busy}
                                  maxLength={240}
                                  value={editingTodoTitle}
                                  onChange={(event) =>
                                    setEditingTodoTitle(event.target.value)
                                  }
                                  onKeyDown={(event) => {
                                    if (
                                      event.key === 'Enter' &&
                                      event.nativeEvent.isComposing
                                    ) {
                                      event.preventDefault();
                                      return;
                                    }
                                    if (event.key === 'Escape') {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      cancelEditingTodo();
                                    }
                                  }}
                                />
                                <button
                                  type="submit"
                                  aria-label={t(
                                    'personalWidgets.todo.saveEdit',
                                  )}
                                  className="shrink-0 rounded-md p-1 text-app-accent transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                                  disabled={
                                    busy || editingTodoTitle.trim().length === 0
                                  }
                                >
                                  {busy ? (
                                    <Loader2
                                      aria-hidden="true"
                                      className="animate-spin"
                                      size={16}
                                    />
                                  ) : (
                                    <Check aria-hidden="true" size={16} />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  aria-label={t(
                                    'personalWidgets.todo.cancelEdit',
                                  )}
                                  className="shrink-0 rounded-md p-1 text-app-ink/40 transition-colors hover:bg-app-surface-hover hover:text-app-ink disabled:opacity-50"
                                  disabled={busy}
                                  onClick={cancelEditingTodo}
                                >
                                  <X aria-hidden="true" size={16} />
                                </button>
                              </form>
                            ) : (
                              <span
                                className={cn(
                                  'app-text-body-sm min-w-0 flex-1 break-words pt-1 text-app-ink',
                                  todo.completed &&
                                    'text-app-ink/45 line-through',
                                )}
                              >
                                {todo.title}
                              </span>
                            )}
                            {!editing ? (
                              <button
                                ref={(node) => {
                                  if (node) {
                                    todoEditButtonRefs.current.set(
                                      todo.id,
                                      node,
                                    );
                                  } else {
                                    todoEditButtonRefs.current.delete(todo.id);
                                  }
                                }}
                                type="button"
                                aria-label={t('personalWidgets.todo.edit', {
                                  title: todo.title,
                                })}
                                className="mt-0.5 shrink-0 rounded-md p-1 text-app-ink/35 transition-colors hover:bg-app-surface-hover hover:text-app-accent disabled:opacity-50"
                                disabled={busy || editingTodoId !== null}
                                onClick={() => startEditingTodo(todo)}
                                title={t('personalWidgets.todo.edit', {
                                  title: todo.title,
                                })}
                              >
                                <Pencil aria-hidden="true" size={16} />
                              </button>
                            ) : null}
                            {!editing && onConvertTodoToPms ? (
                              <button
                                type="button"
                                aria-label={t(
                                  'personalWidgets.todo.convertToPms',
                                  {
                                    title: todo.title,
                                  },
                                )}
                                className="mt-0.5 shrink-0 rounded-md p-1 text-app-ink/35 transition-colors hover:bg-app-surface-hover hover:text-app-accent disabled:opacity-50"
                                disabled={busy}
                                onClick={() => convertTodoToPms(todo)}
                                title={t(
                                  'personalWidgets.todo.convertToPmsShort',
                                )}
                              >
                                <ClipboardList aria-hidden="true" size={16} />
                              </button>
                            ) : null}
                            {!editing ? (
                              <button
                                type="button"
                                aria-label={t('personalWidgets.todo.delete', {
                                  title: todo.title,
                                })}
                                className="mt-0.5 shrink-0 rounded-md p-1 text-app-ink/35 transition-colors hover:bg-app-surface-hover hover:text-[var(--ui-color-danger)] disabled:opacity-50"
                                disabled={busy}
                                onClick={() => void removeTodo(todo)}
                                title={t('personalWidgets.todo.delete', {
                                  title: todo.title,
                                })}
                              >
                                {busy && mutating === 'delete' ? (
                                  <Loader2
                                    aria-hidden="true"
                                    className="animate-spin"
                                    size={16}
                                  />
                                ) : (
                                  <Trash2 aria-hidden="true" size={16} />
                                )}
                              </button>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </section>
            )}
          </div>
        </m.aside>
      ) : null}

      {externalDockPanels
        .filter(
          (panel) =>
            panel.mountInBackgroundOnOpen &&
            backgroundMountedDockPanelIds.has(panel.id) &&
            !(
              mode !== 'collapsed' &&
              activePanelSection === 'dockPanel' &&
              activeDockPanel?.id === panel.id
            ),
        )
        .map((panel) => (
          <div key={panel.id} aria-hidden="true" hidden>
            {panel.renderPanel()}
          </div>
        ))}

      <nav
        aria-label={t('personalWidgets.dockLabel')}
        className="scrollbar-none relative z-[var(--ui-z-dock)] flex h-full w-10 shrink-0 flex-col overflow-x-hidden overflow-y-auto border-l border-app-border bg-app-bg/95 shadow-[var(--ui-shadow-side-dock)] backdrop-blur"
      >
        {dockItems.map((item, index) => {
          const active = mode !== 'collapsed' && activeDockItemId === item.id;
          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.ariaLabel}
              aria-pressed={active}
              className={cn(
                'relative flex min-h-[76px] w-10 flex-col items-center justify-center gap-1 border-app-border px-1 py-2 text-app-ink/60 transition-colors hover:bg-app-surface-hover hover:text-app-ink focus:outline-none focus:ring-2 focus:ring-inset focus:ring-app-accent/35',
                index > 0 && 'border-t',
                active &&
                  'bg-app-accent text-app-accent-fg hover:bg-app-accent hover:text-app-accent-fg',
              )}
              title={item.ariaLabel}
              onClick={() => handleDockItemClick(item.id)}
            >
              <span
                className="flex size-5 shrink-0 items-center justify-center"
                aria-hidden="true"
              >
                {item.renderIcon(15)}
              </span>
              <span className="app-text-micro font-semibold uppercase leading-none [text-orientation:mixed] [writing-mode:vertical-rl]">
                {item.label}
              </span>
              {item.badgeCount && item.badgeCount > 0 ? (
                <span
                  aria-hidden="true"
                  className={cn(
                    'absolute right-1 top-1.5 inline-flex h-4 min-w-4 max-w-8 items-center justify-center rounded-full px-1 text-[0.62rem] font-bold leading-none shadow-sm',
                    item.badgeClassName,
                  )}
                >
                  {item.badgeCount}
                </span>
              ) : item.dirty ? (
                <span
                  aria-hidden="true"
                  className="absolute right-1.5 top-2 size-2.5 rounded-full bg-[var(--ui-color-warning)] shadow-sm"
                />
              ) : null}
            </button>
          );
        })}
      </nav>
    </LazyMotion>
  );
}
