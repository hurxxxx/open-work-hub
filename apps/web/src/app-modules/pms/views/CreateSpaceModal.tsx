import { useState, useEffect, useMemo } from 'react';
import { Layout, UserPlus, X } from 'lucide-react';
import { Dialog, Button } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { hasWorkspaceMembership } from '@/src/platform/auth/auth-api';
import {
  addSpaceMember,
  createSpace,
  listPmsUsers,
  type PmsSpace,
  type PmsUserSummary,
} from '../api/pms-api';
import { initials } from './pms-constants';

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

export const CreateSpaceModal = ({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated?: (space: PmsSpace) => void;
}) => {
  const { t } = useTranslation(['apps', 'common']);
  const { token, user } = useAuth();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [allUsers, setAllUsers] = useState<PmsUserSummary[]>([]);
  const [picked, setPicked] = useState<PmsUserSummary[]>([]);
  const [query, setQuery] = useState('');
  const [queryFocused, setQueryFocused] = useState(false);

  const canCreateSpace = hasWorkspaceMembership(user);

  useEffect(() => {
    if (!isOpen) return;
    setName('');
    setDescription('');
    setError('');
    setSubmitting(false);
    setPicked([]);
    setQuery('');
    setQueryFocused(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !token || !canCreateSpace) return;
    let cancelled = false;
    listPmsUsers(token)
      .then((users) => {
        if (!cancelled) setAllUsers(users);
      })
      .catch(() => {
        if (!cancelled) setAllUsers([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token, canCreateSpace]);

  const pickedIds = useMemo(
    () => new Set(picked.map((u) => u.id)),
    [picked],
  );

  const candidates = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    // Hide the current user — they're added as owner automatically.
    return allUsers
      .filter((u) => u.id !== user?.id && !pickedIds.has(u.id))
      .filter((u) => {
        if (!trimmed) return true;
        return (
          u.full_name.toLowerCase().includes(trimmed) ||
          u.email.toLowerCase().includes(trimmed)
        );
      })
      .slice(0, 6);
  }, [allUsers, pickedIds, query, user?.id]);

  function addMember(u: PmsUserSummary) {
    setPicked((prev) =>
      prev.some((item) => item.id === u.id) ? prev : [...prev, u],
    );
    setQuery('');
  }

  function removeMember(userId: string) {
    setPicked((prev) => prev.filter((u) => u.id !== userId));
  }

  async function handleCreate() {
    if (!token || !name.trim() || !canCreateSpace) return;
    setSubmitting(true);
    setError('');
    try {
      const space = await createSpace(token, {
        name: name.trim(),
        description: description.trim(),
      });

      // Add each picked member sequentially. Failures collect so the user
      // sees exactly which invites couldn't be completed; the space itself
      // is kept regardless so the creator can retry from SpaceMembersModal.
      const failures: string[] = [];
      for (const member of picked) {
        try {
          await addSpaceMember(token, space.id, {
            user_id: member.id,
            role: 'member',
          });
        } catch (err) {
          failures.push(
            `${member.full_name}: ${err instanceof Error ? err.message : t('apps:pms.memberInviteFailed')}`,
          );
        }
      }

      if (failures.length > 0) {
        setError(
          t('apps:pms.createSpacePartialFailure', { failures: failures.join(', ') }),
        );
      }

      onCreated?.(space);
      if (failures.length === 0) {
        onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('apps:pms.createSpaceFailed'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title={t('apps:pms.createSpace')}
      maxWidth="max-w-xl"
      dismissOnInteractOutside={false}
      actions={
        <div className="flex items-center justify-end gap-3 w-full">
          <Button variant="secondary" onClick={onClose}>{t('common:actions.cancel')}</Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            disabled={!name.trim() || !canCreateSpace || submitting}
          >
            {submitting ? t('apps:pms.creating') : t('apps:pms.createSpace')}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 text-app-ink">
        <div className="flex items-center gap-3 p-4 rounded-lg bg-app-surface-sidebar border border-app-border">
          <div className="w-10 h-10 bg-app-accent/20 rounded-lg flex items-center justify-center">
            <Layout size={20} className="text-app-accent" />
          </div>
          <div className="app-text-body text-app-ink/60">
            {t('apps:pms.createSpaceDescription')}
          </div>
        </div>

        {!canCreateSpace && (
          <div className="app-text-body rounded-md border border-[var(--ui-color-warning)]/30 bg-[var(--ui-color-warning)]/10 px-3 py-2 text-[var(--ui-color-warning)]">
            {t('apps:pms.createSpaceNoAccess')}
          </div>
        )}

        {error && (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('apps:pms.spaceName')} <span className="text-[var(--ui-color-danger)]">*</span>
          </label>
          <input
            type="text"
            placeholder={t('apps:pms.spacePlaceholder')}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === 'Enter' &&
                !e.nativeEvent.isComposing &&
                name.trim() &&
                !submitting
              ) {
                handleCreate();
              }
            }}
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none"
            autoFocus
          />
        </div>

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">
            {t('apps:pms.description')} <span className="text-app-ink/30">({t('apps:pms.optional')})</span>
          </label>
          <textarea
            placeholder={t('apps:pms.spaceDescriptionPlaceholder')}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="app-text-body w-full resize-none rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 transition-all focus:border-app-accent focus:outline-none"
          />
        </div>

        {canCreateSpace ? (
          <div className="space-y-2">
            <label className="app-text-control-sm text-app-ink/70">
              {t('apps:pms.inviteMembers')} <span className="text-app-ink/30">({t('apps:pms.optional')})</span>
            </label>
            <p className="app-text-caption text-app-ink/40">
              {t('apps:pms.inviteMembersHint')}
            </p>

            {picked.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {picked.map((member) => (
                  <span
                    key={member.id}
                    className="app-text-caption inline-flex items-center gap-2 rounded-full border border-app-border bg-app-surface-sidebar py-1 pl-1 pr-2 text-app-ink"
                  >
                    <span
                      className={`flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-semibold text-white ${avatarColor(member.id)}`}
                    >
                      {initials(member.full_name)}
                    </span>
                    <span className="max-w-[10rem] truncate">
                      {member.full_name}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeMember(member.id)}
                      className="text-app-ink/40 hover:text-app-ink"
                      aria-label={t('apps:pms.removeMember', { name: member.full_name })}
                    >
                      <X size={11} />
                    </button>
                  </span>
                ))}
              </div>
            ) : null}

            <div className="relative">
              <div className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-app-ink/40">
                <UserPlus size={14} />
              </div>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setQueryFocused(true)}
                onBlur={() => {
                  window.setTimeout(() => setQueryFocused(false), 150);
                }}
                placeholder={t('apps:pms.searchUser')}
                className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar py-2 pl-9 pr-3 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
              />
              {queryFocused && (query.trim() || candidates.length > 0) ? (
                <div className="absolute left-0 right-0 top-full z-10 mt-1 max-h-56 overflow-y-auto rounded-md border border-app-border bg-app-surface shadow-lg">
                  {candidates.length === 0 ? (
                    <div className="app-text-caption px-3 py-3 text-app-ink/40">
                      {query.trim()
                        ? t('apps:pms.noMatchingUsers')
                        : t('apps:pms.noUsersToAdd')}
                    </div>
                  ) : (
                    <ul>
                      {candidates.map((candidate) => (
                        <li key={candidate.id}>
                          <button
                            type="button"
                            onMouseDown={(e) => e.preventDefault()}
                            onClick={() => addMember(candidate)}
                            className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-app-surface-hover"
                          >
                            <span
                              className={`flex h-7 w-7 items-center justify-center rounded-full text-[10px] font-semibold text-white ${avatarColor(candidate.id)}`}
                            >
                              {initials(candidate.full_name)}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="app-text-body line-clamp-1 text-app-ink">
                                {candidate.full_name}
                              </div>
                              <div className="app-text-caption line-clamp-1 text-app-ink/40">
                                {candidate.email}
                              </div>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </Dialog>
  );
};
