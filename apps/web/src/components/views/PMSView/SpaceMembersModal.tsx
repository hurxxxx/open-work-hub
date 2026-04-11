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

import { useAuth } from '@/src/domains/auth/auth-provider';
import { initials } from '@/src/components/views/PMSView/pms-constants';
import {
  addSpaceMember,
  listPmsUsers,
  listSpaceMembers,
  removeSpaceMember,
  updateSpaceMemberRole,
  type PmsSpaceMember,
  type PmsUserSummary,
} from '@/src/domains/pms/pms-api';

interface SpaceMembersModalProps {
  isOpen: boolean;
  onClose: () => void;
  spaceId: string | null;
  spaceName: string;
  canManage: boolean;
  onChanged?: () => void;
}

type RoleValue = 'owner' | 'admin' | 'member' | 'viewer';

const ROLE_OPTIONS: { value: RoleValue; label: string; description: string }[] = [
  { value: 'admin', label: '관리자', description: '멤버 관리 및 설정 변경 가능' },
  { value: 'member', label: '멤버', description: '리스트와 문서 작성 및 편집' },
  { value: 'viewer', label: '뷰어', description: '읽기 전용' },
];

const ROLE_LABELS: Record<string, string> = {
  owner: '소유자',
  admin: '관리자',
  member: '멤버',
  viewer: '뷰어',
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
  if (role === 'owner') {
    return (
      <span className="inline-flex items-center gap-1 text-app-ink/60 dark:text-app-ink/70 app-text-caption">
        <Crown size={12} className="text-amber-500" />
        소유자
      </span>
    );
  }
  if (role === 'admin') {
    return (
      <span className="inline-flex items-center gap-1 text-app-ink/60 dark:text-app-ink/70 app-text-caption">
        <Shield size={12} className="text-app-ink/50" />
        {ROLE_LABELS[role] ?? role}
      </span>
    );
  }
  return (
    <span className="text-app-ink/60 dark:text-app-ink/70 app-text-caption">
      {ROLE_LABELS[role] ?? role}
    </span>
  );
}

interface RowMenuProps {
  open: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  currentRole: RoleValue;
  onChangeRole: (role: RoleValue) => void;
  onRemove: () => void;
}

function RowMenu({
  open,
  anchorRef,
  onClose,
  currentRole,
  onChangeRole,
  onRemove,
}: RowMenuProps) {
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
        역할 변경
      </div>
      {ROLE_OPTIONS.map((role) => (
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
          스페이스에서 제거
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
  onChanged,
}: SpaceMembersModalProps) {
  const { token } = useAuth();
  const [members, setMembers] = useState<PmsSpaceMember[]>([]);
  const [allUsers, setAllUsers] = useState<PmsUserSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [inviteQuery, setInviteQuery] = useState('');
  const [inviteFocused, setInviteFocused] = useState(false);
  const [memberSearch, setMemberSearch] = useState('');
  const [openRowMenu, setOpenRowMenu] = useState<string | null>(null);
  const rowMenuAnchors = useRef<Map<string, HTMLButtonElement | null>>(new Map());

  const refresh = useCallback(async () => {
    if (!token || !spaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [memberRes, users] = await Promise.all([
        listSpaceMembers(token, spaceId),
        canManage ? listPmsUsers(token) : Promise.resolve([] as PmsUserSummary[]),
      ]);
      setMembers(memberRes.items);
      setAllUsers(users);
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버를 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }, [token, spaceId, canManage]);

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
      return a.full_name.localeCompare(b.full_name, 'ko');
    });
    if (!trimmed) return sorted;
    return sorted.filter((member) => {
      return (
        member.full_name.toLowerCase().includes(trimmed) ||
        member.email.toLowerCase().includes(trimmed)
      );
    });
  }, [members, memberSearch]);

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
      setError(err instanceof Error ? err.message : '멤버를 추가할 수 없습니다.');
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
      setError(err instanceof Error ? err.message : '역할을 변경할 수 없습니다.');
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRemove(userId: string) {
    if (!token || !spaceId) return;
    if (!window.confirm('이 멤버를 스페이스에서 제거하시겠습니까?')) return;
    setBusyUserId(userId);
    setError(null);
    try {
      await removeSpaceMember(token, spaceId, userId);
      await refresh();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버를 제거할 수 없습니다.');
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
            멤버 관리
          </span>
        </span>
      }
      maxWidth="max-w-2xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
        </div>
      }
    >
      <div className="space-y-6 text-app-ink">
        {!canManage ? (
          <div className="app-text-caption rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink/60 dark:text-app-ink/70">
            이 스페이스의 멤버를 수정할 권한이 없습니다. 현재 멤버만 볼 수 있습니다.
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
            <h3 className="app-text-overline text-app-ink/50">멤버 초대</h3>
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
                placeholder="이름 또는 이메일로 사용자 검색"
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar py-2 pl-9 pr-3 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
              {inviteFocused && (inviteQuery.trim() || inviteCandidates.length > 0) ? (
                <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-md border border-app-border bg-app-surface shadow-lg">
                  {inviteCandidates.length === 0 ? (
                    <div className="app-text-caption px-3 py-3 text-app-ink/40">
                      {inviteQuery.trim()
                        ? '일치하는 사용자가 없습니다.'
                        : '추가할 수 있는 사용자가 없습니다.'}
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
                            <MemberAvatar name={user.full_name} seed={user.id} />
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
              초대된 멤버는 기본 "멤버" 역할로 추가됩니다. 역할은 아래 리스트에서 변경할 수 있습니다.
            </p>
          </section>
        ) : null}

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="app-text-overline text-app-ink/50">
              멤버 · {members.length}
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
                  placeholder="멤버 검색"
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
                ? '검색 결과가 없습니다.'
                : '아직 멤버가 없습니다.'}
            </p>
          ) : (
            <ul className="divide-y divide-app-border rounded-md border border-app-border bg-app-surface">
              {visibleMembers.map((member) => {
                const isBusy = busyUserId === member.user_id;
                const canMutate = canManage && member.role !== 'owner';
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
                            aria-label="멤버 작업"
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
