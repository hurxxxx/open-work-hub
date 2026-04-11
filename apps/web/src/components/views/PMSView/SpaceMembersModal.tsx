import { useCallback, useEffect, useMemo, useState } from 'react';
import { Dialog, Button } from '@aidoo/ui';
import { Loader2, Trash2, UserPlus } from 'lucide-react';

import { useAuth } from '@/src/domains/auth/auth-provider';
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
  /** Whether the current user is allowed to mutate the member list. */
  canManage: boolean;
  /** Called after any change so the caller can refresh space lists. */
  onChanged?: () => void;
}

const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: 'owner', label: '소유자' },
  { value: 'admin', label: '관리자' },
  { value: 'member', label: '멤버' },
  { value: 'viewer', label: '뷰어' },
];

function roleLabel(value: string): string {
  return ROLE_OPTIONS.find((item) => item.value === value)?.label ?? value;
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
  const [query, setQuery] = useState('');
  const [pickerFocused, setPickerFocused] = useState(false);
  const [newMemberRole, setNewMemberRole] = useState('member');

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
    setQuery('');
    setPickerFocused(false);
    setNewMemberRole('member');
    setError(null);
    refresh();
  }, [isOpen, spaceId, refresh]);

  const memberIds = useMemo(
    () => new Set(members.map((member) => member.user_id)),
    [members],
  );

  const filteredCandidates = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    return allUsers
      .filter((user) => !memberIds.has(user.id))
      .filter((user) => {
        if (!trimmed) return true;
        return (
          user.full_name.toLowerCase().includes(trimmed) ||
          user.email.toLowerCase().includes(trimmed)
        );
      })
      .slice(0, 8);
  }, [allUsers, memberIds, query]);

  async function handleAdd(user: PmsUserSummary) {
    if (!token || !spaceId) return;
    setBusyUserId(user.id);
    setError(null);
    try {
      await addSpaceMember(token, spaceId, {
        user_id: user.id,
        role: newMemberRole,
      });
      await refresh();
      onChanged?.();
      setQuery('');
    } catch (err) {
      setError(err instanceof Error ? err.message : '멤버를 추가할 수 없습니다.');
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleRoleChange(userId: string, role: string) {
    if (!token || !spaceId) return;
    setBusyUserId(userId);
    setError(null);
    try {
      await updateSpaceMemberRole(token, spaceId, userId, role);
      await refresh();
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : '역할을 변경할 수 없습니다.',
      );
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
      title={`${spaceName} · 멤버 관리`}
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>
            닫기
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        {!canManage ? (
          <div className="app-text-body rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink/70">
            이 스페이스의 멤버를 수정할 권한이 없습니다. 현재 멤버 목록만 볼 수 있습니다.
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
          <div className="space-y-2">
            <label className="app-text-control-sm text-app-ink/70">
              멤버 추가
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setPickerFocused(true)}
                onBlur={() => {
                  window.setTimeout(() => setPickerFocused(false), 150);
                }}
                placeholder="이름 또는 이메일로 검색"
                className="app-text-body flex-1 rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
              <select
                value={newMemberRole}
                onChange={(e) => setNewMemberRole(e.target.value)}
                className="app-text-body rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink focus:border-app-accent focus:outline-none"
              >
                {ROLE_OPTIONS.filter((role) => role.value !== 'owner').map(
                  (role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ),
                )}
              </select>
            </div>
            {pickerFocused ? (
              <div className="max-h-44 overflow-y-auto rounded-md border border-app-border bg-app-surface">
                {filteredCandidates.length === 0 ? (
                  <div className="app-text-caption px-3 py-2 text-app-ink/40">
                    {query.trim()
                      ? '일치하는 사용자가 없습니다.'
                      : '이름 또는 이메일을 입력하세요.'}
                  </div>
                ) : (
                  <ul>
                    {filteredCandidates.map((user) => (
                      <li key={user.id}>
                        <button
                          type="button"
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={() => handleAdd(user)}
                          disabled={busyUserId !== null}
                          className="app-text-body flex w-full items-center justify-between px-3 py-2 text-left text-app-ink hover:bg-app-surface-hover disabled:opacity-50"
                        >
                          <span className="inline-flex items-center gap-2">
                            <UserPlus
                              size={12}
                              className="text-app-ink/40"
                            />
                            {user.full_name}
                          </span>
                          <span className="app-text-caption text-app-ink/40">
                            {user.email}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="app-text-control-sm text-app-ink/70">
              현재 멤버
            </label>
            <span className="app-text-caption text-app-ink/40">
              {members.length}명
            </span>
          </div>
          {loading ? (
            <div className="flex h-24 items-center justify-center text-app-ink/40">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : members.length === 0 ? (
            <p className="app-text-caption rounded-md border border-dashed border-app-border px-3 py-4 text-center text-app-ink/50">
              아직 멤버가 없습니다.
            </p>
          ) : (
            <ul className="space-y-1">
              {members.map((member) => (
                <li
                  key={member.user_id}
                  className="flex items-center justify-between rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="app-text-body line-clamp-1 text-app-ink">
                      {member.full_name}
                    </p>
                    <p className="app-text-caption text-app-ink/40">
                      {member.email}
                    </p>
                  </div>
                  <div className="ml-2 flex shrink-0 items-center gap-1">
                    {canManage && member.role !== 'owner' ? (
                      <select
                        value={member.role}
                        onChange={(e) =>
                          handleRoleChange(member.user_id, e.target.value)
                        }
                        disabled={busyUserId === member.user_id}
                        className="app-text-caption rounded-md border border-app-border bg-app-surface px-2 py-1 text-app-ink focus:border-app-accent focus:outline-none disabled:opacity-50"
                      >
                        {ROLE_OPTIONS.filter(
                          (role) => role.value !== 'owner',
                        ).map((role) => (
                          <option key={role.value} value={role.value}>
                            {role.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="app-text-caption text-app-ink/60 dark:text-app-ink/70">
                        {roleLabel(member.role)}
                      </span>
                    )}
                    {canManage && member.role !== 'owner' ? (
                      <button
                        type="button"
                        onClick={() => handleRemove(member.user_id)}
                        disabled={busyUserId === member.user_id}
                        className="rounded-md p-1.5 text-app-ink/40 hover:bg-app-surface-hover hover:text-[var(--ui-color-danger)] disabled:opacity-40"
                        aria-label="멤버 제거"
                        title="제거"
                      >
                        <Trash2 size={14} />
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Dialog>
  );
}

export default SpaceMembersModal;
