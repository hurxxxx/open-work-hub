import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, Button } from '@aidoo/ui';
import {
  Check,
  Crown,
  Loader2,
  MoreHorizontal,
  Search,
  Shield,
  UserPlus,
} from 'lucide-react';
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
import { initials } from './pms-constants';

interface SpaceMembersModalProps {
  isOpen: boolean;
  onClose: () => void;
  spaceId: string | null;
  spaceName: string;
  canManage: boolean;
  currentUserRole?: string | null;
  onChanged?: () => void;
}

type RoleValue = 'owner' | 'admin' | 'member' | 'viewer';

const ROLE_OPTIONS: { value: RoleValue; labelKey: string; descriptionKey: string }[] =
  [
    {
      value: 'admin',
      labelKey: 'pms.settings.role.admin',
      descriptionKey: 'pms.spaceMembers.roleDescription.admin',
    },
    {
      value: 'member',
      labelKey: 'pms.settings.role.member',
      descriptionKey: 'pms.spaceMembers.roleDescription.member',
    },
    {
      value: 'viewer',
      labelKey: 'pms.settings.role.viewer',
      descriptionKey: 'pms.spaceMembers.roleDescription.viewer',
    },
  ];

const OWNER_ROLE_OPTION: {
  value: RoleValue;
  labelKey: string;
  descriptionKey: string;
} = {
  value: 'owner',
  labelKey: 'pms.settings.role.owner',
  descriptionKey: 'pms.spaceMembers.roleDescription.owner',
};

const ROLE_LABEL_KEYS: Record<string, string> = {
  owner: 'pms.settings.role.owner',
  admin: 'pms.settings.role.admin',
  member: 'pms.settings.role.member',
  viewer: 'pms.settings.role.viewer',
};

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
  const label = ROLE_LABEL_KEYS[role] ? t(ROLE_LABEL_KEYS[role]) : role;
  if (role === 'owner') {
    return (
      <span className="inline-flex items-center gap-1 text-app-ink/60 dark:text-app-ink/70 app-text-caption">
        <Crown size={12} className="text-amber-500" />
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
  anchorRef: React.RefObject<HTMLButtonElement | null>;
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
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open || !anchorRef.current) return;
    const rect = anchorRef.current.getBoundingClientRect();
    setPos({ top: rect.bottom + 4, left: rect.right - 200 });
  }, [open, anchorRef]);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      ref={ref}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[10000] w-[200px] overflow-hidden rounded-lg border border-app-border bg-app-bg py-1 shadow-xl"
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
        <span className="w-3 shrink-0" />
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
  onClose,
  spaceId,
  spaceName,
  canManage,
  currentUserRole = null,
  onChanged,
}: SpaceMembersModalProps) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [members, setMembers] = useState<PmsSpaceMember[]>([]);
  const [allUsers, setAllUsers] = useState<PmsUserSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [inviteQuery, setInviteQuery] = useState('');
  const [inviteFocused, setInviteFocused] = useState(false);
  const [memberSearch, setMemberSearch] = useState('');
  const [openRowMenu, setOpenRowMenu] = useState<string | null>(null);
  const rowMenuAnchors = useRef<Map<string, HTMLButtonElement | null>>(
    new Map(),
  );
  const canManageAdmins = currentUserRole === 'owner';
  const roleOptionConfig = useMemo(
    () =>
      canManageAdmins ? [OWNER_ROLE_OPTION, ...ROLE_OPTIONS] : ROLE_OPTIONS,
    [canManageAdmins],
  );
  const roleOptions = useMemo(
    () => roleOptionConfig.map((option) => ({
      value: option.value,
      label: t(option.labelKey),
      description: t(option.descriptionKey),
    })),
    [roleOptionConfig, t],
  );

  const refresh = useCallback(async () => {
    if (!token || !spaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [memberRes, users] = await Promise.all([
        listSpaceMembers(token, spaceId),
        canManage
          ? listPmsUsers(token)
          : Promise.resolve([] as PmsUserSummary[]),
      ]);
      setMembers(memberRes.items);
      setAllUsers(users);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('pms.spaceMembers.errors.loadFailed'),
      );
    } finally {
      setLoading(false);
    }
  }, [token, spaceId, canManage, t]);

  useEffect(() => {
    if (!isOpen || !spaceId) return;
    setInviteQuery('');
    setInviteFocused(false);
    setMemberSearch('');
    setOpenRowMenu(null);
    setError(null);
    refresh();
  }, [isOpen, spaceId, refresh]);

  const memberIds = useMemo(
    () => new Set(members.map((member) => member.user_id)),
    [members],
  );

  const inviteCandidates = useMemo(() => {
    const trimmed = inviteQuery.trim().toLowerCase();
    return allUsers
      .filter((user) => !memberIds.has(user.id))
      .filter((user) => {
        if (!trimmed) return true;
        return (
          user.full_name.toLowerCase().includes(trimmed) ||
          user.email.toLowerCase().includes(trimmed)
        );
      })
      .slice(0, 6);
  }, [allUsers, memberIds, inviteQuery]);

  const visibleMembers = useMemo(() => {
    const trimmed = memberSearch.trim().toLowerCase();
    const sorted = [...members].sort((a, b) => {
      // Owners always first, then admins, then alphabetical.
      const rank: Record<string, number> = {
        owner: 0,
        admin: 1,
        member: 2,
        viewer: 3,
      };
      const ra = rank[a.role] ?? 4;
      const rb = rank[b.role] ?? 4;
      if (ra !== rb) return ra - rb;
      return a.full_name.localeCompare(b.full_name, locale);
    });
    if (!trimmed) return sorted;
    return sorted.filter((member) => {
      return (
        member.full_name.toLowerCase().includes(trimmed) ||
        member.email.toLowerCase().includes(trimmed)
      );
    });
  }, [members, memberSearch, locale]);

  async function handleInvite(user: PmsUserSummary) {
    if (!token || !spaceId) return;
    setBusyUserId(user.id);
    setError(null);
    try {
      await addSpaceMember(token, spaceId, {
        user_id: user.id,
        role: 'member',
      });
      await refresh();
      onChanged?.();
      setInviteQuery('');
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('pms.spaceMembers.errors.addFailed'),
      );
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRoleChange(userId: string, role: RoleValue) {
    if (!token || !spaceId) return;
    setBusyUserId(userId);
    setError(null);
    try {
      await updateSpaceMemberRole(token, spaceId, userId, role);
      await refresh();
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('pms.spaceMembers.errors.changeRoleFailed'),
      );
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRemove(userId: string) {
    if (!token || !spaceId) return;
    if (!window.confirm(t('pms.spaceMembers.removeConfirm'))) return;
    setBusyUserId(userId);
    setError(null);
    try {
      await removeSpaceMember(token, spaceId, userId);
      await refresh();
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t('pms.spaceMembers.errors.removeFailed'),
      );
    } finally {
      setBusyUserId(null);
    }
  }

  return (
    <Dialog
      open={isOpen}
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
            <h3 className="app-text-overline text-app-ink/50">{t('pms.spaceMembers.inviteTitle')}</h3>
            <div className="relative">
              <div className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/40">
                <UserPlus size={14} />
              </div>
              <input
                type="text"
                value={inviteQuery}
                onChange={(e) => setInviteQuery(e.target.value)}
                onFocus={() => setInviteFocused(true)}
                onBlur={() => {
                  window.setTimeout(() => setInviteFocused(false), 150);
                }}
                placeholder={t('pms.searchUser')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar py-2 pl-9 pr-3 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
              {inviteFocused &&
              (inviteQuery.trim() || inviteCandidates.length > 0) ? (
                <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-md border border-app-border bg-app-surface shadow-lg">
                  {inviteCandidates.length === 0 ? (
                    <div className="app-text-caption px-3 py-3 text-app-ink/40">
                      {inviteQuery.trim()
                        ? t('pms.noMatchingUsers')
                        : t('pms.noUsersToAdd')}
                    </div>
                  ) : (
                    <ul>
                      {inviteCandidates.map((user) => (
                        <li key={user.id}>
                          <button
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => handleInvite(user)}
                            disabled={busyUserId !== null}
                            className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-app-surface-hover disabled:opacity-50"
                          >
                            <MemberAvatar
                              name={user.full_name}
                              seed={user.id}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="app-text-body line-clamp-1 text-app-ink">
                                {user.full_name}
                              </div>
                              <div className="app-text-caption line-clamp-1 text-app-ink/40">
                                {user.email}
                              </div>
                            </div>
                            {busyUserId === user.id ? (
                              <Loader2
                                size={14}
                                className="animate-spin text-app-ink/40"
                              />
                            ) : null}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}
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
                  onChange={(e) => setMemberSearch(e.target.value)}
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
                const isSelf = member.user_id === user?.id;
                const canMutate =
                  canManage &&
                  !isSelf &&
                  (canManageAdmins ||
                    (member.role !== 'owner' && member.role !== 'admin'));
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
                              rowMenuAnchors.current.set(member.user_id, el);
                            }}
                            type="button"
                            onClick={() =>
                              setOpenRowMenu((current) =>
                                current === member.user_id
                                  ? null
                                  : member.user_id,
                              )
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
                                rowMenuAnchors.current.get(member.user_id) ??
                                null,
                            }}
                            onClose={() => setOpenRowMenu(null)}
                            currentRole={member.role as RoleValue}
                            roleOptions={roleOptions}
                            onChangeRole={(role) =>
                              handleRoleChange(member.user_id, role)
                            }
                            onRemove={() => handleRemove(member.user_id)}
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
  );
}

export default SpaceMembersModal;
