import { SpaceGroupBindings } from './SpaceGroupBindings';
import { Button, Dialog, useConfirm } from '@open-work-hub/ui';
import {
  Check,
  Crown,
  Loader2,
  MoreHorizontal,
  Search,
  Shield,
  UserMinus,
  UserPlus,
} from 'lucide-react';
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useMemo,
  useReducer,
  useRef,
  type RefObject,
} from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  addSpaceMember,
  listPmsUsers,
  listSpaceMembers,
  removeSpaceMember,
  updateSpaceMemberRole,
  type PmsSpaceMember,
  type PmsUserSummary,
} from '../api/pms-api';
import { MemberSuggestionDropdown } from './MemberSuggestionDropdown';
import { initials } from './pms-constants';
import { dispatchPmsSpaceMembersChanged } from './pms-events';
import {
  canMutateSpaceMember,
  roleOptionConfigForUser,
  inviteCandidates as selectInviteCandidates,
  SPACE_MEMBER_ROLE_LABEL_KEYS,
  SPACE_MEMBER_ROW_MENU_ESTIMATED_HEIGHT,
  SPACE_MEMBERS_INITIAL_STATE,
  spaceMemberIds,
  spaceMemberRowMenuPosition,
  spaceMembersModalReducer,
  visibleSpaceMembers,
  type RoleValue,
} from './space-members-modal-model';

interface SpaceMembersModalProps {
  isOpen: boolean;
  onClose: () => void;
  spaceId: string | null;
  spaceName: string;

  canManage: boolean;
  currentUserRole?: string | null;
  onChanged?: () => void;
}

/**
 * Pick a deterministic tailwind background color for an avatar based on a
 * string hash. Keeps colors stable across renders for the same user.
 */
const AVATAR_COLORS = [
  'bg-rose-500',
  'bg-pink-500',
  'bg-fuchsia-500',
  'bg-purple-500',
  'bg-violet-500',
  'bg-indigo-500',
  'bg-blue-500',
  'bg-sky-500',
  'bg-cyan-500',
  'bg-teal-500',
  'bg-emerald-500',
  'bg-green-500',
  'bg-amber-500',
  'bg-orange-500',
];

function avatarColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function MemberAvatar({ name, seed }: { name: string; seed: string }) {
  return (
    <div
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white ${avatarColor(seed)}`}
    >
      {initials(name)}
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  const { t } = useTranslation('apps');
  const label = SPACE_MEMBER_ROLE_LABEL_KEYS[role]
    ? t(SPACE_MEMBER_ROLE_LABEL_KEYS[role])
    : role;
  if (role === 'owner') {
    return (
      <span className="inline-flex items-center gap-1 text-app-ink/60 dark:text-app-ink/70 app-text-caption">
        <Crown size={12} className="text-app-warning" />
        {label}
      </span>
    );
  }
  if (role === 'admin') {
    return (
      <span className="inline-flex items-center gap-1 text-app-ink/60 dark:text-app-ink/70 app-text-caption">
        <Shield size={12} className="text-app-ink/50" />
        {label}
      </span>
    );
  }
  return (
    <span className="text-app-ink/60 dark:text-app-ink/70 app-text-caption">
      {label}
    </span>
  );
}

interface RowMenuProps {
  open: boolean;
  anchorRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  currentRole: RoleValue;
  roleOptions: { value: RoleValue; label: string; description: string }[];
  onChangeRole: (role: RoleValue) => void;
  onRemove: () => void;
}

function RowMenu({
  open,
  anchorRef,
  onClose,
  currentRole,
  roleOptions,
  onChangeRole,
  onRemove,
}: RowMenuProps) {
  const { t } = useTranslation('apps');
  const ref = useRef<HTMLDivElement>(null);
  const anchorRect = open ? anchorRef.current?.getBoundingClientRect() : null;
  const pos = anchorRect
    ? spaceMemberRowMenuPosition({
        anchorRect,
        menuHeight:
          ref.current?.offsetHeight ?? SPACE_MEMBER_ROW_MENU_ESTIMATED_HEIGHT,
        viewportHeight: window.innerHeight,
        viewportWidth: window.innerWidth,
      })
    : { top: 0, left: 0 };
  const closeFromDocumentEvent = useEffectEvent(onClose);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        closeFromDocumentEvent();
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [closeFromDocumentEvent, open]);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      data-ui-floating-layer=""
      className="pointer-events-auto fixed z-[10000] max-h-[calc(100vh-1rem)] w-[200px] overflow-y-auto rounded-lg border border-app-border bg-app-bg py-1 shadow-xl"
    >
      <div className="px-3 py-1 app-text-overline text-app-ink/40">
        {t('pms.spaceMembers.changeRole')}
      </div>
      {roleOptions.map((role) => (
        <button
          key={role.value}
          type="button"
          onClick={() => {
            onChangeRole(role.value);
            onClose();
          }}
          className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-app-surface-hover"
        >
          <div className="mt-0.5 w-3 shrink-0">
            {role.value === currentRole ? (
              <Check size={12} className="text-app-accent" />
            ) : null}
          </div>
          <div className="min-w-0 flex-1">
            <div className="app-text-control-sm text-app-ink">{role.label}</div>
            <div className="app-text-caption text-app-ink/40">
              {role.description}
            </div>
          </div>
        </button>
      ))}
      <div className="my-1 border-t border-app-border" />
      <button
        type="button"
        onClick={() => {
          onRemove();
          onClose();
        }}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-app-surface-hover"
      >
        <UserMinus
          size={12}
          className="w-3 shrink-0 text-[var(--ui-color-danger)]"
        />
        <span className="app-text-control-sm text-[var(--ui-color-danger)]">
          {t('pms.spaceMembers.removeFromSpace')}
        </span>
      </button>
    </div>,
    document.body,
  );
}

export function SpaceMembersModal({
  isOpen,
  spaceId,
  ...props
}: SpaceMembersModalProps) {
  if (!isOpen || !spaceId) {
    return null;
  }
  return (
    <SpaceMembersModalContent key={spaceId} spaceId={spaceId} {...props} />
  );
}

type SpaceMembersModalContentProps = Omit<
  SpaceMembersModalProps,
  'isOpen' | 'spaceId'
> & {
  spaceId: string;
};

function SpaceMembersModalContent(props: SpaceMembersModalContentProps) {
  return useSpaceMembersModalContentElement(props);
}

function useSpaceMembersModalContentElement({
  onClose,
  spaceId,
  spaceName,
  canManage,
  currentUserRole = null,
  onChanged,
}: SpaceMembersModalContentProps) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('apps');
  const { confirm, confirmDialog } = useConfirm();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [state, dispatch] = useReducer(
    spaceMembersModalReducer,
    SPACE_MEMBERS_INITIAL_STATE,
  );
  const {
    members,
    allUsers,
    loading,
    error,
    busyUserId,
    inviteQuery,
    inviteFocused,
    memberSearch,
    openRowMenu,
  } = state;
  const rowMenuAnchors = useRef<Map<string, HTMLButtonElement | null> | null>(
    null,
  );
  if (rowMenuAnchors.current === null) {
    rowMenuAnchors.current = new Map();
  }
  const rowMenuAnchorMap = rowMenuAnchors.current;
  const canManageAdmins = currentUserRole === 'owner';
  const roleOptionConfig = useMemo(
    () => roleOptionConfigForUser(canManageAdmins),
    [canManageAdmins],
  );
  const roleOptions = useMemo(
    () =>
      roleOptionConfig.map((option) => ({
        value: option.value,
        label: t(option.labelKey),
        description: t(option.descriptionKey),
      })),
    [roleOptionConfig, t],
  );

  const refresh = useCallback(async () => {
    if (!token) return;
    dispatch({ type: 'loadStart' });
    try {
      const [memberRes, users] = await Promise.all([
        listSpaceMembers(token, spaceId),
        canManage
          ? listPmsUsers(token)
          : Promise.resolve([] as PmsUserSummary[]),
      ]);
      dispatch({
        type: 'loadSuccess',
        members: memberRes.items,
        users,
      });
    } catch (err) {
      dispatch({
        type: 'loadFailure',
        error:
          err instanceof Error
            ? err.message
            : t('pms.spaceMembers.errors.loadFailed'),
      });
    }
  }, [token, spaceId, canManage, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const memberIds = useMemo(() => spaceMemberIds(members), [members]);

  const inviteCandidates = useMemo(() => {
    return selectInviteCandidates({
      allUsers,
      currentUserId: user?.id,
      memberIds,
      query: inviteQuery,
    });
  }, [allUsers, memberIds, inviteQuery, user?.id]);

  const visibleMembers = useMemo(() => {
    return visibleSpaceMembers({
      locale,
      members,
      query: memberSearch,
    });
  }, [members, memberSearch, locale]);

  async function handleInvite(user: PmsUserSummary) {
    if (!token) return;
    dispatch({ type: 'setBusyUserId', busyUserId: user.id });
    dispatch({ type: 'setError', error: null });
    try {
      await addSpaceMember(token, spaceId, {
        user_id: user.id,
        role: 'member',
      });
      await refresh();
      dispatchPmsSpaceMembersChanged(spaceId);
      onChanged?.();
      dispatch({ type: 'setInviteQuery', inviteQuery: '' });
    } catch (err) {
      dispatch({
        type: 'setError',
        error:
          err instanceof Error
            ? err.message
            : t('pms.spaceMembers.errors.addFailed'),
      });
    } finally {
      dispatch({ type: 'setBusyUserId', busyUserId: null });
    }
  }

  async function handleRoleChange(userId: string, role: RoleValue) {
    if (!token) return;
    dispatch({ type: 'setBusyUserId', busyUserId: userId });
    dispatch({ type: 'setError', error: null });
    try {
      await updateSpaceMemberRole(token, spaceId, userId, role);
      await refresh();
      dispatchPmsSpaceMembersChanged(spaceId);
      onChanged?.();
    } catch (err) {
      dispatch({
        type: 'setError',
        error:
          err instanceof Error
            ? err.message
            : t('pms.spaceMembers.errors.changeRoleFailed'),
      });
    } finally {
      dispatch({ type: 'setBusyUserId', busyUserId: null });
    }
  }

  async function handleRemove(member: PmsSpaceMember) {
    if (!token) return;
    const confirmed = await confirm({
      title: t('pms.spaceMembers.removeConfirmTitle'),
      description: t('pms.spaceMembers.removeConfirmDescription', {
        name: member.full_name,
      }),
      confirmLabel: t('pms.spaceMembers.removeConfirmAction'),
      cancelLabel: t('common:actions.cancel'),
      variant: 'danger',
    });
    if (!confirmed) return;
    dispatch({ type: 'setBusyUserId', busyUserId: member.user_id });
    dispatch({ type: 'setError', error: null });
    try {
      await removeSpaceMember(token, spaceId, member.user_id);
      await refresh();
      dispatchPmsSpaceMembersChanged(spaceId);
      onChanged?.();
    } catch (err) {
      dispatch({
        type: 'setError',
        error:
          err instanceof Error
            ? err.message
            : t('pms.spaceMembers.errors.removeFailed'),
      });
    } finally {
      dispatch({ type: 'setBusyUserId', busyUserId: null });
    }
  }

  return (
    <>
      <Dialog
        closeLabel={t('common:actions.close')}
        open
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        title={
          <span className="inline-flex items-baseline gap-2">
            <span>{spaceName}</span>
            <span className="app-text-caption font-normal text-app-ink/40">
              {t('pms.spaceMembers.titleSuffix')}
            </span>
          </span>
        }
        maxWidth="max-w-2xl"
        dismissOnInteractOutside={false}
        actions={
          <div className="flex w-full items-center justify-end">
            <Button variant="secondary" onClick={onClose}>
              {t('common:actions.close')}
            </Button>
          </div>
        }
      >
        <div className="space-y-6 text-app-ink">
          {token && spaceId ? (
            <SpaceGroupBindings
              key={spaceId}
              token={token}
              resourceId={spaceId}
              canManage={canManage}
              canManageAdmins={canManageAdmins}
            />
          ) : null}
          {!canManage ? (
            <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink/60 dark:text-app-ink/70">
              {t('pms.spaceMembers.readOnlyNotice')}
            </div>
          ) : null}

          {error ? (
            <div
              role="alert"
              className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
            >
              {error}
            </div>
          ) : null}

          {canManage ? (
            <section className="space-y-2">
              <h3 className="app-text-overline text-app-ink/50">
                {t('pms.spaceMembers.inviteTitle')}
              </h3>
              <div className="relative">
                <div className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/40">
                  <UserPlus size={14} />
                </div>
                <input
                  type="text"
                  value={inviteQuery}
                  onChange={(e) =>
                    dispatch({
                      type: 'setInviteQuery',
                      inviteQuery: e.target.value,
                    })
                  }
                  onFocus={() =>
                    dispatch({ type: 'setInviteFocused', inviteFocused: true })
                  }
                  onBlur={() => {
                    window.setTimeout(() => {
                      dispatch({
                        type: 'setInviteFocused',
                        inviteFocused: false,
                      });
                    }, 150);
                  }}
                  aria-label={t('pms.searchUser')}
                  placeholder={t('pms.searchUser')}
                  className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar py-2 pl-9 pr-3 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
                />
                <MemberSuggestionDropdown
                  candidates={inviteCandidates}
                  currentUserId={user?.id}
                  currentUserLabel={t('pms.taskDetail.me')}
                  isCandidateDisabled={() => busyUserId !== null}
                  noMatchingLabel={t('pms.noMatchingUsers')}
                  noUsersLabel={t('pms.noUsersToAdd')}
                  onSelect={handleInvite}
                  open={
                    inviteFocused &&
                    (Boolean(inviteQuery.trim()) || inviteCandidates.length > 0)
                  }
                  query={inviteQuery}
                  renderTrailing={(candidate) =>
                    busyUserId === candidate.id ? (
                      <Loader2
                        size={14}
                        className="animate-spin text-app-ink/40"
                      />
                    ) : null
                  }
                />
              </div>
              <p className="app-text-caption text-app-ink/40">
                {t('pms.spaceMembers.inviteHint')}
              </p>
            </section>
          ) : null}

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="app-text-overline text-app-ink/50">
                {t('pms.spaceMembers.memberCount', { count: members.length })}
              </h3>
              {members.length > 5 ? (
                <div className="relative">
                  <div className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-app-ink/30">
                    <Search size={12} />
                  </div>
                  <input
                    type="text"
                    value={memberSearch}
                    onChange={(e) =>
                      dispatch({
                        type: 'setMemberSearch',
                        memberSearch: e.target.value,
                      })
                    }
                    aria-label={t('pms.spaceMembers.memberSearchPlaceholder')}
                    placeholder={t('pms.spaceMembers.memberSearchPlaceholder')}
                    className="app-text-caption w-44 rounded-md border border-app-border bg-app-surface-sidebar py-1 pl-7 pr-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
                  />
                </div>
              ) : null}
            </div>

            {loading ? (
              <div className="flex h-24 items-center justify-center text-app-ink/40">
                <Loader2 size={16} className="animate-spin" />
              </div>
            ) : visibleMembers.length === 0 ? (
              <p className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-6 text-center text-app-ink/50">
                {memberSearch.trim()
                  ? t('common:empty.noResults')
                  : t('pms.spaceMembers.noMembers')}
              </p>
            ) : (
              <ul className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface">
                {visibleMembers.map((member) => {
                  const isBusy = busyUserId === member.user_id;
                  const canMutate = canMutateSpaceMember({
                    canManage,
                    canManageAdmins,
                    currentUserId: user?.id,
                    member,
                  });
                  return (
                    <li
                      key={member.user_id}
                      className="group flex items-center gap-3 px-3 py-2.5 transition-colors hover:bg-app-surface-hover"
                    >
                      <MemberAvatar
                        name={member.full_name}
                        seed={member.user_id}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="app-text-body line-clamp-1 font-medium text-app-ink">
                          {member.full_name}
                        </div>
                        <div className="app-text-caption line-clamp-1 text-app-ink/40">
                          {member.email}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <RoleBadge role={member.role} />
                        {canMutate ? (
                          <>
                            <button
                              ref={(el) => {
                                rowMenuAnchorMap.set(member.user_id, el);
                              }}
                              type="button"
                              onClick={() =>
                                dispatch({
                                  type: 'toggleRowMenu',
                                  userId: member.user_id,
                                })
                              }
                              disabled={isBusy}
                              className="rounded-md p-1 text-app-ink/40 opacity-0 transition-opacity hover:bg-app-surface hover:text-app-ink group-hover:opacity-100 focus:opacity-100 disabled:opacity-40"
                              aria-label={t('pms.spaceMembers.memberActions')}
                            >
                              {isBusy ? (
                                <Loader2 size={14} className="animate-spin" />
                              ) : (
                                <MoreHorizontal size={14} />
                              )}
                            </button>
                            <RowMenu
                              open={openRowMenu === member.user_id}
                              anchorRef={{
                                current:
                                  rowMenuAnchorMap.get(member.user_id) ?? null,
                              }}
                              onClose={() =>
                                dispatch({
                                  type: 'setOpenRowMenu',
                                  openRowMenu: null,
                                })
                              }
                              currentRole={member.role as RoleValue}
                              roleOptions={roleOptions}
                              onChangeRole={(role) =>
                                handleRoleChange(member.user_id, role)
                              }
                              onRemove={() => void handleRemove(member)}
                            />
                          </>
                        ) : (
                          // Keep horizontal alignment consistent with rows that
                          // do have the overflow button.
                          <span className="w-6" aria-hidden="true" />
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </Dialog>
      {confirmDialog}
    </>
  );
}
