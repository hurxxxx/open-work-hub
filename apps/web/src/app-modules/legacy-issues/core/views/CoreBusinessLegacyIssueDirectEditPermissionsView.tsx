import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import { useToast } from '@ai-do/ui';

import { listWorkspaceMembers } from '@/src/platform/admin/admin-api';
import { hasAdminConsoleAccess } from '@/src/platform/auth/auth-api';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  UserOptionAvatar,
  UserSearchMultiSelect,
} from '@/src/platform/users/UserSearchMultiSelect';
import { useWorkspaceBootstrapContext } from '@/src/platform/workspaces/workspace-bootstrap-context';
import {
  fetchLegacyIssueModuleDirectEditors,
  grantLegacyIssueModuleDirectEditor,
  revokeLegacyIssueModuleDirectEditor,
  type LegacyIssueModuleDirectEditor,
} from '../api/legacy-issue-direct-edit-permissions-api';
import {
  LEGACY_ISSUE_MODULE_VIEW_KEYS,
  LEGACY_ISSUE_VIEWS,
  type LegacyIssueModuleViewKey,
} from '../legacy-issue-datasets';
import {
  LegacyIssuePageHeader,
  LegacyIssueToolbarButton,
} from './LegacyIssuePageParts';

type WorkspaceUserCandidate = {
  id: string;
  email: string;
  full_name: string;
};

export function CoreBusinessLegacyIssueDirectEditPermissionsView() {
  const { workspaceSlug = '' } = useParams<{ workspaceSlug: string }>();
  const { token, user } = useAuth();
  const { data: workspaceBootstrap } = useWorkspaceBootstrapContext();
  const { t } = useTranslation(['apps', 'common', 'shell']);
  const toast = useToast();
  const canManage = hasAdminConsoleAccess(user);
  const moduleKeys = useMemo(() => {
    if (!workspaceBootstrap) {
      return [...LEGACY_ISSUE_MODULE_VIEW_KEYS];
    }
    const navItemIds = new Set(workspaceBootstrap.nav.map((item) => item.id));
    return LEGACY_ISSUE_MODULE_VIEW_KEYS.filter((moduleKey) =>
      navItemIds.has(LEGACY_ISSUE_VIEWS[moduleKey].navItemId),
    );
  }, [workspaceBootstrap]);
  const [items, setItems] = useState<LegacyIssueModuleDirectEditor[]>([]);
  const [loading, setLoading] = useState(true);
  const [queryByModule, setQueryByModule] = useState<
    Partial<Record<LegacyIssueModuleViewKey, string>>
  >({});
  const [focusedModuleKey, setFocusedModuleKey] =
    useState<LegacyIssueModuleViewKey | null>(null);
  const [candidates, setCandidates] = useState<WorkspaceUserCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [savingPermissionKeys, setSavingPermissionKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const loadRequestIdRef = useRef(0);
  const activeQuery = focusedModuleKey
    ? (queryByModule[focusedModuleKey] ?? '')
    : '';

  const loadItems = useCallback(async () => {
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    if (!canManage || !workspaceSlug || !token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setItems([]);
    try {
      const response = await fetchLegacyIssueModuleDirectEditors({
        token,
        workspaceSlug,
      });
      if (loadRequestIdRef.current === requestId) {
        setItems(response.items);
      }
    } catch (error) {
      if (loadRequestIdRef.current === requestId) {
        toast.error(
          errorMessage(
            error,
            t('coreBusiness.directEditPermissions.errors.loadFailed'),
          ),
        );
      }
    } finally {
      if (loadRequestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [canManage, t, toast, token, workspaceSlug]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  useEffect(() => {
    const workspaceId = workspaceBootstrap?.workspace.id;
    if (!canManage || !workspaceId || !token || !focusedModuleKey) {
      setCandidates([]);
      setSearching(false);
      return;
    }
    let cancelled = false;
    setCandidates([]);
    setSearching(true);
    const handle = window.setTimeout(() => {
      void listWorkspaceMembers(token, workspaceId, {
        page: 1,
        pageSize: 30,
        q: activeQuery,
        subjectType: 'user',
      })
        .then((response) => {
          if (cancelled) return;
          setCandidates(
            response.items
              .filter(
                (item) =>
                  item.subject_type === 'user' && item.user_status === 'active',
              )
              .map((item) => ({
                email: item.subject_secondary ?? '',
                full_name: item.subject_label,
                id: item.subject_id,
              })),
          );
        })
        .catch((error) => {
          if (!cancelled) {
            setCandidates([]);
            toast.error(
              errorMessage(
                error,
                t('coreBusiness.directEditPermissions.errors.searchFailed'),
              ),
            );
          }
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [
    activeQuery,
    canManage,
    focusedModuleKey,
    t,
    toast,
    token,
    workspaceBootstrap?.workspace.id,
  ]);

  async function grantUser(
    moduleKey: LegacyIssueModuleViewKey,
    candidate: WorkspaceUserCandidate,
  ) {
    const permissionKey = permissionTargetKey(moduleKey, candidate.id);
    const alreadySelected = items.some(
      (item) => item.module_key === moduleKey && item.user_id === candidate.id,
    );
    if (
      !canManage ||
      !workspaceSlug ||
      !token ||
      savingPermissionKeys.has(permissionKey) ||
      alreadySelected
    ) {
      return;
    }
    setSavingPermission(moduleKey, candidate.id, true);
    try {
      const granted = await grantLegacyIssueModuleDirectEditor({
        moduleKey,
        token,
        userId: candidate.id,
        workspaceSlug,
      });
      setItems((current) => [
        ...current.filter(
          (item) =>
            item.module_key !== granted.module_key ||
            item.user_id !== granted.user_id,
        ),
        granted,
      ]);
      setModuleQuery(moduleKey, '');
      toast.success(
        t('coreBusiness.directEditPermissions.status.granted', {
          name: granted.display_name,
        }),
      );
    } catch (error) {
      toast.error(
        errorMessage(
          error,
          t('coreBusiness.directEditPermissions.errors.grantFailed'),
        ),
      );
    } finally {
      setSavingPermission(moduleKey, candidate.id, false);
    }
  }

  async function revokeUser(
    moduleKey: LegacyIssueModuleViewKey,
    userId: string,
  ) {
    const permissionKey = permissionTargetKey(moduleKey, userId);
    const item = items.find(
      (candidate) =>
        candidate.module_key === moduleKey && candidate.user_id === userId,
    );
    if (
      !item?.can_revoke ||
      !canManage ||
      !workspaceSlug ||
      !token ||
      savingPermissionKeys.has(permissionKey)
    ) {
      return;
    }
    setSavingPermission(moduleKey, userId, true);
    try {
      await revokeLegacyIssueModuleDirectEditor({
        moduleKey,
        token,
        userId,
        workspaceSlug,
      });
      setItems((current) =>
        current.filter(
          (candidate) =>
            candidate.module_key !== moduleKey || candidate.user_id !== userId,
        ),
      );
      toast.success(
        t('coreBusiness.directEditPermissions.status.revoked', {
          name: item.display_name,
        }),
      );
    } catch (error) {
      toast.error(
        errorMessage(
          error,
          t('coreBusiness.directEditPermissions.errors.revokeFailed'),
        ),
      );
    } finally {
      setSavingPermission(moduleKey, userId, false);
    }
  }

  function setModuleQuery(moduleKey: LegacyIssueModuleViewKey, query: string) {
    setQueryByModule((current) => ({ ...current, [moduleKey]: query }));
  }

  function setModuleQueryFocused(
    moduleKey: LegacyIssueModuleViewKey,
    focused: boolean,
  ) {
    setFocusedModuleKey((current) => {
      if (focused) return moduleKey;
      return current === moduleKey ? null : current;
    });
  }

  function setSavingPermission(
    moduleKey: LegacyIssueModuleViewKey,
    userId: string,
    saving: boolean,
  ) {
    const permissionKey = permissionTargetKey(moduleKey, userId);
    setSavingPermissionKeys((current) => {
      const next = new Set(current);
      if (saving) {
        next.add(permissionKey);
      } else {
        next.delete(permissionKey);
      }
      return next;
    });
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-app-bg">
      <LegacyIssuePageHeader
        actions={
          <LegacyIssueToolbarButton
            disabled={loading || savingPermissionKeys.size > 0}
            icon={
              loading ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <RefreshCw size={16} />
              )
            }
            label={t('common:actions.reload')}
            onClick={() => void loadItems()}
          />
        }
        eyebrow={t('coreBusiness.directEditPermissions.eyebrow')}
        title={t('coreBusiness.directEditPermissions.title')}
      />

      <main className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-6xl space-y-4">
          <section className="rounded-lg border border-app-border bg-app-surface p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck
                size={20}
                className="mt-0.5 shrink-0 text-app-accent"
              />
              <div className="min-w-0">
                <h2 className="app-text-body font-semibold text-app-ink">
                  {t('coreBusiness.directEditPermissions.scopeTitle')}
                </h2>
                <p className="mt-1 app-text-body-sm text-app-ink/60">
                  {t('coreBusiness.directEditPermissions.scopeNotice')}
                </p>
                <p className="mt-1 app-text-caption text-app-ink/45">
                  {t(
                    'coreBusiness.directEditPermissions.platformAdminImplicit',
                  )}
                </p>
                <p className="mt-2 app-text-body-sm text-app-ink/60">
                  {t('coreBusiness.directEditPermissions.description')}
                </p>
              </div>
            </div>
          </section>

          <div className="grid items-start gap-4 lg:grid-cols-2">
            {moduleKeys.map((moduleKey) => {
              const moduleItems = items.filter(
                (item) => item.module_key === moduleKey,
              );
              const selectedUserIds = new Set(
                moduleItems.map((item) => item.user_id),
              );
              const availableCandidates =
                focusedModuleKey === moduleKey
                  ? candidates.filter(
                      (candidate) => !selectedUserIds.has(candidate.id),
                    )
                  : [];
              const moduleSaving = Array.from(savingPermissionKeys).some(
                (permissionKey) => permissionKey.startsWith(`${moduleKey}:`),
              );
              const query = queryByModule[moduleKey] ?? '';
              const queryFocused = focusedModuleKey === moduleKey;

              return (
                <section
                  key={moduleKey}
                  className="rounded-lg border border-app-border bg-app-surface"
                >
                  <div className="flex items-center justify-between gap-3 border-b border-app-border px-4 py-3">
                    <h2 className="app-text-body font-semibold text-app-ink">
                      {t(
                        `shell:nav.${LEGACY_ISSUE_VIEWS[moduleKey].navItemId}`,
                      )}
                    </h2>
                    <span className="app-text-caption shrink-0 rounded-full bg-app-accent/10 px-2 py-1 text-app-accent">
                      {t('coreBusiness.directEditPermissions.assignedCount', {
                        count: moduleItems.length,
                      })}
                    </span>
                  </div>

                  <div className="space-y-3 p-4">
                    <UserSearchMultiSelect
                      candidates={availableCandidates}
                      density="compact"
                      disabled={!canManage || loading || moduleSaving}
                      inputId={`legacy-issue-direct-edit-user-search-${moduleKey}`}
                      labels={{
                        noUserMatch: t('common:empty.noResults'),
                        removeItem: (name) =>
                          t('coreBusiness.directEditPermissions.removeUser', {
                            name,
                          }),
                        searchPlaceholder: t(
                          'coreBusiness.directEditPermissions.searchPlaceholder',
                        ),
                        searchPrompt: t(
                          'coreBusiness.directEditPermissions.searchPrompt',
                        ),
                        searching: t('common:feedback.loading'),
                      }}
                      loading={searching && queryFocused}
                      onAddUser={(candidate) =>
                        void grantUser(moduleKey, candidate)
                      }
                      onQueryChange={(nextQuery) =>
                        setModuleQuery(moduleKey, nextQuery)
                      }
                      onQueryFocusChange={(focused) =>
                        setModuleQueryFocused(moduleKey, focused)
                      }
                      onRemoveUser={(userId) =>
                        void revokeUser(moduleKey, userId)
                      }
                      query={query}
                      queryFocused={queryFocused}
                      selectedUsers={[]}
                    />

                    {loading ? (
                      <div className="flex items-center gap-2 py-6 app-text-body-sm text-app-ink/50">
                        <Loader2 size={16} className="animate-spin" />
                        {t('common:feedback.loading')}
                      </div>
                    ) : moduleItems.length === 0 ? (
                      <div className="rounded-md border border-dashed border-app-border px-4 py-6 text-center app-text-body-sm text-app-ink/45">
                        {t('coreBusiness.directEditPermissions.empty')}
                      </div>
                    ) : (
                      <ul className="divide-y divide-app-border rounded-md border border-app-border">
                        {moduleItems.map((item) => {
                          const busy = savingPermissionKeys.has(
                            permissionTargetKey(moduleKey, item.user_id),
                          );
                          const userOption = {
                            email: item.email,
                            full_name: item.display_name,
                            id: item.user_id,
                          };
                          return (
                            <li
                              key={item.id}
                              className="flex items-center gap-3 px-3 py-2.5"
                            >
                              <UserOptionAvatar user={userOption} />
                              <div className="min-w-0 flex-1">
                                <p className="truncate app-text-body-sm font-medium text-app-ink">
                                  {item.display_name}
                                </p>
                                <p className="truncate app-text-caption text-app-ink/45">
                                  {item.email}
                                </p>
                              </div>
                              {!item.can_revoke ? (
                                <span className="app-text-caption text-app-ink/45">
                                  {t(
                                    'coreBusiness.directEditPermissions.inheritedRole',
                                  )}
                                </span>
                              ) : (
                                <div className="flex items-center gap-2">
                                  {!item.active_member ? (
                                    <span className="app-text-caption text-amber-600 dark:text-amber-400">
                                      {t(
                                        'coreBusiness.directEditPermissions.inactiveMember',
                                      )}
                                    </span>
                                  ) : null}
                                  <button
                                    type="button"
                                    className="app-control h-8 px-2.5"
                                    aria-label={t(
                                      'coreBusiness.directEditPermissions.removeUser',
                                      { name: item.display_name },
                                    )}
                                    disabled={busy}
                                    onClick={() =>
                                      void revokeUser(moduleKey, item.user_id)
                                    }
                                  >
                                    {busy ? (
                                      <Loader2
                                        size={14}
                                        className="animate-spin"
                                      />
                                    ) : (
                                      <X size={14} />
                                    )}
                                    {t(
                                      'coreBusiness.directEditPermissions.actions.revoke',
                                    )}
                                  </button>
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}

function permissionTargetKey(
  moduleKey: LegacyIssueModuleViewKey,
  userId: string,
): string {
  return `${moduleKey}:${userId}`;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
