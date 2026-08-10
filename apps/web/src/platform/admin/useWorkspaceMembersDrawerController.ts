import { useCallback, useEffect, useMemo, useState } from 'react';

import type {
  WorkspaceItem,
  WorkspaceMemberItem,
  WorkspaceMembersResponse,
} from './admin-api';
import { getErrorMessage } from './admin-shared';
import {
  activeWorkspaceMemberSelection,
  selectableWorkspaceMemberKeys,
  toggleWorkspaceMemberPageSelection,
  toggleWorkspaceMemberSelectionKey,
  workspaceMemberKey,
  workspaceMembersAllSelectableSelected,
} from './workspace-members-model';
import {
  bulkRemoveWorkspaceMembersWorkflow,
  bulkUpdateWorkspaceMemberRolesWorkflow,
  changeWorkspaceMemberRoleWorkflow,
  loadWorkspaceMembersPageWorkflow,
  removeWorkspaceMemberWorkflow,
  type WorkspaceMembersWorkflowPorts,
} from './workspace-members-workflow';

export interface WorkspaceMembersDrawerMessages {
  loadFailed: string;
  roleChanged: string;
  roleChangeFailed: string;
  removed: string;
  removeFailed: string;
  bulkRemovePartial(succeeded: number, failed: number): string;
  bulkRemoved(count: number): string;
  bulkRemoveFailed: string;
  bulkRolePartial(succeeded: number, failed: number): string;
  bulkRoleChanged(count: number): string;
  bulkRoleFailed: string;
}

export interface WorkspaceMembersDrawerControllerOptions {
  open: boolean;
  workspace: WorkspaceItem | null;
  currentUserId: string;
  ports: WorkspaceMembersWorkflowPorts;
  messages: WorkspaceMembersDrawerMessages;
  onChanged: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
  debounceMs?: number;
  pageSize?: number;
}

export interface WorkspaceMembersDrawerController {
  state: {
    bulkRoleOpen: boolean;
    busy: boolean;
    data: WorkspaceMembersResponse | null;
    loading: boolean;
    page: number;
    pendingOnly: boolean;
    query: string;
    roleFilter: string | null;
  };
  derived: {
    activeSelectedKeys: Set<string>;
    allSelectableKeys: string[];
    allSelectableSelected: boolean;
    totalPages: number;
  };
  actions: {
    bulkRemove(): Promise<void>;
    bulkRole(role: string): Promise<void>;
    clearSelection(): void;
    reload(): Promise<void>;
    setBulkRoleOpen(open: boolean | ((current: boolean) => boolean)): void;
    setPage(page: number | ((current: number) => number)): void;
    setPendingOnly(pendingOnly: boolean): void;
    setQuery(query: string): void;
    setRoleFilter(roleFilter: string | null): void;
    singleRemove(item: WorkspaceMemberItem): Promise<void>;
    singleRoleChange(item: WorkspaceMemberItem, role: string): Promise<void>;
    toggleSelect(item: WorkspaceMemberItem): void;
    toggleSelectAll(): void;
  };
}

export function useWorkspaceMembersDrawerController({
  open,
  workspace,
  currentUserId,
  ports,
  messages,
  onChanged,
  onError,
  onSuccess,
  debounceMs = 200,
  pageSize = 25,
}: WorkspaceMembersDrawerControllerOptions): WorkspaceMembersDrawerController {
  const [data, setData] = useState<WorkspaceMembersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [query, setQueryState] = useState('');
  const [roleFilter, setRoleFilterState] = useState<string | null>(null);
  const [pendingOnly, setPendingOnlyState] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [bulkRoleOpen, setBulkRoleOpen] = useState(false);

  const reload = useCallback(async () => {
    if (!workspace) return;
    setLoading(true);
    try {
      const response = await loadWorkspaceMembersPageWorkflow({
        workspaceId: workspace.id,
        listState: {
          query,
          roleFilter,
          page,
          pageSize,
          pendingOnly,
        },
        ports,
      });
      setData(response);
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, messages.loadFailed));
    } finally {
      setLoading(false);
    }
  }, [
    messages.loadFailed,
    onError,
    page,
    pageSize,
    pendingOnly,
    ports,
    query,
    roleFilter,
    workspace,
  ]);

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => void reload(), debounceMs);
    return () => window.clearTimeout(handle);
  }, [debounceMs, open, reload]);

  const totalPages = data
    ? Math.max(1, Math.ceil(data.total / data.page_size))
    : 1;
  const selectableKeys = useMemo(
    () => selectableWorkspaceMemberKeys(data?.items ?? [], currentUserId),
    [currentUserId, data?.items],
  );
  const activeSelectedKeys = useMemo(
    () => activeWorkspaceMemberSelection(selectedKeys, selectableKeys),
    [selectableKeys, selectedKeys],
  );
  const allSelectableKeys = useMemo(
    () => Array.from(selectableKeys),
    [selectableKeys],
  );
  const allSelectableSelected = workspaceMembersAllSelectableSelected(
    allSelectableKeys,
    activeSelectedKeys,
  );

  const setQuery = useCallback((nextQuery: string) => {
    setQueryState(nextQuery);
    setPage(1);
  }, []);

  const setRoleFilter = useCallback((nextRoleFilter: string | null) => {
    setRoleFilterState(nextRoleFilter);
    setPendingOnlyState(false);
    setPage(1);
  }, []);

  const setPendingOnly = useCallback((nextPendingOnly: boolean) => {
    setPendingOnlyState(nextPendingOnly);
    if (nextPendingOnly) {
      setRoleFilterState(null);
    }
    setPage(1);
  }, []);

  const toggleSelect = useCallback((item: WorkspaceMemberItem) => {
    const key = workspaceMemberKey(item);
    setSelectedKeys((current) =>
      toggleWorkspaceMemberSelectionKey(current, key),
    );
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedKeys((current) =>
      toggleWorkspaceMemberPageSelection(
        current,
        allSelectableKeys,
        allSelectableSelected,
      ),
    );
  }, [allSelectableKeys, allSelectableSelected]);

  const singleRoleChange = useCallback(
    async (item: WorkspaceMemberItem, role: string) => {
      if (!workspace) return;
      setBusy(true);
      try {
        await changeWorkspaceMemberRoleWorkflow({
          workspaceId: workspace.id,
          member: item,
          role,
          ports,
        });
        onSuccess(messages.roleChanged);
        onChanged();
        await reload();
      } catch (caughtError) {
        onError(getErrorMessage(caughtError, messages.roleChangeFailed));
      } finally {
        setBusy(false);
      }
    },
    [
      messages.roleChangeFailed,
      messages.roleChanged,
      onChanged,
      onError,
      onSuccess,
      ports,
      reload,
      workspace,
    ],
  );

  const singleRemove = useCallback(
    async (item: WorkspaceMemberItem) => {
      if (!workspace) return;
      setBusy(true);
      try {
        await removeWorkspaceMemberWorkflow({
          workspaceId: workspace.id,
          member: item,
          ports,
        });
        onSuccess(messages.removed);
        onChanged();
        await reload();
      } catch (caughtError) {
        onError(getErrorMessage(caughtError, messages.removeFailed));
      } finally {
        setBusy(false);
      }
    },
    [
      messages.removeFailed,
      messages.removed,
      onChanged,
      onError,
      onSuccess,
      ports,
      reload,
      workspace,
    ],
  );

  const bulkRemove = useCallback(async () => {
    if (!workspace) return;
    if (activeSelectedKeys.size === 0) return;
    setBusy(true);
    try {
      const { outcome } = await bulkRemoveWorkspaceMembersWorkflow({
        workspaceId: workspace.id,
        selectedKeys: activeSelectedKeys,
        ports,
      });
      if (outcome.partial) {
        onError(messages.bulkRemovePartial(outcome.succeeded, outcome.failedCount));
      } else {
        onSuccess(messages.bulkRemoved(outcome.succeeded));
      }
      setSelectedKeys(new Set());
      onChanged();
      await reload();
    } catch (caughtError) {
      onError(getErrorMessage(caughtError, messages.bulkRemoveFailed));
    } finally {
      setBusy(false);
    }
  }, [
    activeSelectedKeys,
    messages,
    onChanged,
    onError,
    onSuccess,
    ports,
    reload,
    workspace,
  ]);

  const bulkRole = useCallback(
    async (role: string) => {
      if (!workspace) return;
      if (activeSelectedKeys.size === 0) return;
      setBulkRoleOpen(false);
      setBusy(true);
      try {
        const { outcome } = await bulkUpdateWorkspaceMemberRolesWorkflow({
          workspaceId: workspace.id,
          selectedKeys: activeSelectedKeys,
          role,
          ports,
        });
        if (outcome.partial) {
          onError(messages.bulkRolePartial(outcome.succeeded, outcome.failedCount));
        } else {
          onSuccess(messages.bulkRoleChanged(outcome.succeeded));
        }
        setSelectedKeys(new Set());
        onChanged();
        await reload();
      } catch (caughtError) {
        onError(getErrorMessage(caughtError, messages.bulkRoleFailed));
      } finally {
        setBusy(false);
      }
    },
    [
      activeSelectedKeys,
      messages,
      onChanged,
      onError,
      onSuccess,
      ports,
      reload,
      workspace,
    ],
  );

  return {
    state: {
      bulkRoleOpen,
      busy,
      data,
      loading,
      page,
      pendingOnly,
      query,
      roleFilter,
    },
    derived: {
      activeSelectedKeys,
      allSelectableKeys,
      allSelectableSelected,
      totalPages,
    },
    actions: {
      bulkRemove,
      bulkRole,
      clearSelection: () => setSelectedKeys(new Set()),
      reload,
      setBulkRoleOpen,
      setPage,
      setPendingOnly,
      setQuery,
      setRoleFilter,
      singleRemove,
      singleRoleChange,
      toggleSelect,
      toggleSelectAll,
    },
  };
}
