import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion } from 'motion/react';
import { X, Plus, Pencil, Trash2, Check, Loader2 } from 'lucide-react';
import { Button, InlineNotice, Select } from '@aidoo/ui';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/src/platform/auth/auth-provider';
import { formatDateTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  addSpaceMember,
  listTaskListLabels,
  listPmsUsers,
  createTaskListLabel,
  updateLabel,
  deleteLabel,
  listSpaceMembers,
  listTaskListStatuses,
  createTaskListStatus,
  updateTaskListStatus,
  deleteTaskListStatus,
  updateSpaceMemberRole,
  removeSpaceMember,
  type PmsLabel,
  type PmsSpaceMember,
  type PmsTaskListStatus,
  type PmsUserSummary,
} from '../api/pms-api';

const PRESET_COLORS = [
  '#b45309', '#1d4ed8', '#0f766e', '#7c3aed', '#dc2626',
  '#16a34a', '#ca8a04', '#0284c7', '#9333ea', '#e11d48',
];

const CATEGORY_OPTIONS = [
  { value: 'backlog', labelKey: 'pms.settings.category.backlog' },
  { value: 'active', labelKey: 'pms.settings.category.active' },
  { value: 'done', labelKey: 'pms.settings.category.done' },
  { value: 'canceled', labelKey: 'pms.settings.category.canceled' },
];

const ROLE_OPTIONS = [
  { value: 'owner', labelKey: 'pms.settings.role.owner' },
  { value: 'admin', labelKey: 'pms.settings.role.admin' },
  { value: 'member', labelKey: 'pms.settings.role.member' },
  { value: 'viewer', labelKey: 'pms.settings.role.viewer' },
];

export function TaskListSettingsPanel({
  taskListId,
  teamId,
  currentUserRole,
  onClose,
  onLabelsChanged,
  onStatusesChanged,
}: {
  taskListId: string;
  teamId: string | null;
  currentUserRole: string | null;
  onClose: () => void;
  onLabelsChanged?: (labels: PmsLabel[]) => void;
  onStatusesChanged?: (statuses: PmsTaskListStatus[]) => void;
}) {
  const { token, user } = useAuth();
  const { t, i18n } = useTranslation('apps');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [members, setMembers] = useState<PmsSpaceMember[]>([]);
  const [availableUsers, setAvailableUsers] = useState<PmsUserSummary[]>([]);
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [statuses, setStatuses] = useState<PmsTaskListStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState(PRESET_COLORS[0]);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Status management state
  const [newStatusName, setNewStatusName] = useState('');
  const [newStatusColor, setNewStatusColor] = useState('#3b82f6');
  const [newStatusCategory, setNewStatusCategory] = useState('active');
  const [creatingStatus, setCreatingStatus] = useState(false);
  const [editingStatusId, setEditingStatusId] = useState<string | null>(null);
  const [editStatusName, setEditStatusName] = useState('');
  const [editStatusColor, setEditStatusColor] = useState('');
  const [editStatusCategory, setEditStatusCategory] = useState('');
  const [selectedUserId, setSelectedUserId] = useState('__none__');
  const [selectedRole, setSelectedRole] = useState('member');
  const [addingMember, setAddingMember] = useState(false);
  const canManageAdmins = currentUserRole === 'owner';
  const availableRoleOptions = useMemo(
    () => (canManageAdmins ? ROLE_OPTIONS : ROLE_OPTIONS.filter((option) => option.value === 'member' || option.value === 'viewer')),
    [canManageAdmins],
  );
  const categoryLabels = useMemo(
    () => new Map(CATEGORY_OPTIONS.map((option) => [option.value, t(option.labelKey)])),
    [t],
  );

  const notifyParent = useCallback((updated: PmsLabel[]) => {
    onLabelsChanged?.(updated);
  }, [onLabelsChanged]);

  const notifyStatusParent = useCallback((updated: PmsTaskListStatus[]) => {
    onStatusesChanged?.(updated);
  }, [onStatusesChanged]);

  const loadAll = useCallback(async () => {
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      const [memberRes, userItems, labelRes, statusRes] = await Promise.all([
        teamId ? listSpaceMembers(token, teamId) : Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }),
        listPmsUsers(token),
        listTaskListLabels(token, taskListId),
        listTaskListStatuses(token, taskListId),
      ]);
      setMembers(memberRes.items);
      setAvailableUsers(userItems);
      setLabels(labelRes.items);
      notifyParent(labelRes.items);
      setStatuses(statusRes.items);
      notifyStatusParent(statusRes.items);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [notifyParent, notifyStatusParent, taskListId, teamId, token, t]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleCreate = useCallback(async () => {
    if (!token || !newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const label = await createTaskListLabel(token, taskListId, { name: newName.trim(), color: newColor });
      const updated = [...labels, label];
      setLabels(updated);
      notifyParent(updated);
      setNewName('');
      setNewColor(PRESET_COLORS[0]);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.createLabelFailed'));
    } finally {
      setCreating(false);
    }
  }, [token, taskListId, newName, newColor, labels, notifyParent, t]);

  const startEdit = (label: PmsLabel) => {
    setEditingId(label.id);
    setEditName(label.name);
    setEditColor(label.color);
  };

  const handleSaveEdit = useCallback(async () => {
    if (!token || !editingId || !editName.trim()) return;
    setError(null);
    try {
      const updatedLabel = await updateLabel(token, editingId, { name: editName.trim(), color: editColor });
      const updated = labels.map(l => l.id === editingId ? updatedLabel : l);
      setLabels(updated);
      notifyParent(updated);
      setEditingId(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.updateLabelFailed'));
    }
  }, [token, editingId, editName, editColor, labels, notifyParent, t]);

  const handleDelete = useCallback(async (labelId: string) => {
    if (!token) return;
    setError(null);
    try {
      await deleteLabel(token, labelId);
      const updated = labels.filter(l => l.id !== labelId);
      setLabels(updated);
      notifyParent(updated);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.deleteLabelFailed'));
    }
  }, [token, labels, notifyParent, t]);

  // ── Status handlers ──
  const handleCreateStatus = useCallback(async () => {
    if (!token || !newStatusName.trim()) return;
    setCreatingStatus(true);
    setError(null);
    try {
      const ps = await createTaskListStatus(token, taskListId, {
        name: newStatusName.trim(),
        color: newStatusColor,
        category: newStatusCategory,
        sort_order: statuses.length,
      });
      const updated = [...statuses, ps];
      setStatuses(updated);
      notifyStatusParent(updated);
      setNewStatusName('');
      setNewStatusColor('#3b82f6');
      setNewStatusCategory('active');
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.createStatusFailed'));
    } finally {
      setCreatingStatus(false);
    }
  }, [token, taskListId, newStatusName, newStatusColor, newStatusCategory, statuses, notifyStatusParent, t]);

  const startEditStatus = (ps: PmsTaskListStatus) => {
    setEditingStatusId(ps.id);
    setEditStatusName(ps.name);
    setEditStatusColor(ps.color);
    setEditStatusCategory(ps.category);
  };

  const handleSaveEditStatus = useCallback(async () => {
    if (!token || !editingStatusId || !editStatusName.trim()) return;
    setError(null);
    try {
      const updated = await updateTaskListStatus(token, editingStatusId, {
        name: editStatusName.trim(),
        color: editStatusColor,
        category: editStatusCategory,
      });
      const next = statuses.map(s => s.id === editingStatusId ? updated : s);
      setStatuses(next);
      notifyStatusParent(next);
      setEditingStatusId(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.updateStatusFailed'));
    }
  }, [token, editingStatusId, editStatusName, editStatusColor, editStatusCategory, statuses, notifyStatusParent, t]);

  const handleDeleteStatus = useCallback(async (statusId: string) => {
    if (!token) return;
    setError(null);
    try {
      await deleteTaskListStatus(token, statusId);
      const updated = statuses.filter(s => s.id !== statusId);
      setStatuses(updated);
      notifyStatusParent(updated);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.deleteStatusFailed'));
    }
  }, [token, statuses, notifyStatusParent, t]);

  const handleAddMember = useCallback(async () => {
    if (!token || !teamId || selectedUserId === '__none__') return;
    setAddingMember(true);
    setError(null);
    try {
      const added = await addSpaceMember(token, teamId, {
        user_id: selectedUserId,
        role: selectedRole,
      });
      setMembers((current) => [...current, added]);
      setSelectedUserId('__none__');
      setSelectedRole('member');
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.addMemberFailed'));
    } finally {
      setAddingMember(false);
    }
  }, [selectedRole, selectedUserId, teamId, token, t]);

  const handleRoleChange = useCallback(async (userId: string, role: string) => {
    if (!token || !teamId) return;
    setError(null);
    try {
      const updatedMember = await updateSpaceMemberRole(token, teamId, userId, role);
      setMembers((current) => current.map((member) => (
        member.user_id === userId ? updatedMember : member
      )));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.updateMemberRoleFailed'));
    }
  }, [teamId, token, t]);

  const handleRemoveMember = useCallback(async (userId: string) => {
    if (!token || !teamId) return;
    setError(null);
    try {
      await removeSpaceMember(token, teamId, userId);
      setMembers((current) => current.filter((member) => member.user_id !== userId));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t('pms.settings.errors.removeMemberFailed'));
    }
  }, [teamId, token, t]);

  const memberCandidateOptions = useMemo(() => [
    { value: '__none__', label: t('pms.settings.addMemberByEmail') },
    ...availableUsers
      .filter((user) => !members.some((member) => member.user_id === user.id))
      .map((user) => ({
        value: user.id,
        label: `${user.full_name} (${user.email})`,
      })),
  ], [availableUsers, members, t]);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-app-bg border-l border-app-border shadow-2xl flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-app-border shrink-0">
          <h2 className="app-text-title-md text-app-ink">{t('pms.settings.title')}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t('common:actions.close')}><X size={16} /></Button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-4 space-y-6">
          <section className="space-y-3">
            <h3 className="app-text-overline text-app-ink/50">{t('pms.settings.members')}</h3>

            {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

            {teamId ? (
              <div className="grid gap-2 rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-3">
                <Select
                  onValueChange={setSelectedUserId}
                  options={memberCandidateOptions}
                  value={selectedUserId}
                />
                <div className="flex items-center gap-2">
                  <select
                    value={selectedRole}
                    onChange={(event) => setSelectedRole(event.target.value)}
                    className="app-text-caption flex-1 rounded border border-app-border bg-app-bg px-2 py-2 text-app-ink focus:outline-none"
                  >
                    {availableRoleOptions.map((option) => (
                      <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
                    ))}
                  </select>
                  <Button
                    disabled={selectedUserId === '__none__' || addingMember}
                    onClick={() => { void handleAddMember(); }}
                    variant="secondary"
                  >
                    {t('common:actions.add')}
                  </Button>
                </div>
              </div>
            ) : null}

            {loading ? (
              <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-app-ink/40" /></div>
            ) : (
              <div className="space-y-2">
                {members.map((member) => {
                  const isProtectedManager = !canManageAdmins && (member.role === 'owner' || member.role === 'admin');
                  const isSelf = member.user_id === user?.id;
                  return (
                  <div key={member.user_id} className="rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="app-text-body truncate font-medium text-app-ink">{member.full_name}</div>
                        <div className="app-text-caption truncate text-app-ink/45">{member.email}</div>
                      </div>
                      <button
                        disabled={isProtectedManager || isSelf}
                        onClick={() => { void handleRemoveMember(member.user_id); }}
                        className="text-app-ink/35 hover:text-red-400 transition-colors disabled:cursor-not-allowed disabled:text-app-ink/20"
                        title={t('pms.settings.removeMember')}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <div className="app-text-micro text-app-ink/35">
                        {t('pms.settings.joined', { date: formatDateTime(member.joined_at, {
                          dateStyle: 'medium',
                          locale,
                          timeZone,
                        }) })}
                      </div>
                      <select
                        disabled={isProtectedManager || isSelf}
                        value={member.role}
                        onChange={(event) => { void handleRoleChange(member.user_id, event.target.value); }}
                        className="app-text-caption rounded border border-app-border bg-app-bg px-2 py-1 text-app-ink focus:outline-none"
                      >
                        {(canManageAdmins
                          ? ROLE_OPTIONS
                          : availableRoleOptions
                        ).map((option) => (
                          <option key={option.value} value={option.value}>{t(option.labelKey)}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                );})}
              </div>
            )}
          </section>

          {/* Labels section */}
          <section className="space-y-3">
            <h3 className="app-text-overline text-app-ink/50">{t('pms.settings.labels')}</h3>

            {loading ? (
              <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-app-ink/40" /></div>
            ) : (
              <div className="space-y-1">
                {labels.map(label => (
                  <div key={label.id} className="flex items-center gap-2 py-1.5 group">
                    {editingId === label.id ? (
                      <>
                        <ColorDot color={editColor} />
                        <input
                          autoFocus
                          value={editName}
                          onChange={e => setEditName(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') handleSaveEdit(); if (e.key === 'Escape') setEditingId(null); }}
                          className="app-text-body flex-1 rounded border border-app-border bg-app-surface-sidebar px-2 py-0.5 text-app-ink focus:border-app-accent focus:outline-none"
                        />
                        <ColorPicker value={editColor} onChange={setEditColor} />
                        <button onClick={handleSaveEdit} className="text-app-accent hover:opacity-80" aria-label={t('pms.settings.saveLabel')}>
                          <Check size={14} />
                        </button>
                      </>
                    ) : (
                      <>
                        <ColorDot color={label.color} />
                        <span className="app-text-body flex-1 text-app-ink">{label.name}</span>
                        <button
                          onClick={() => startEdit(label)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-ink transition-all"
                          aria-label={t('pms.settings.editLabel', { name: label.name })}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDelete(label.id)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-red-400 transition-all"
                          aria-label={t('pms.settings.deleteLabel', { name: label.name })}
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Add new label */}
            <div className="flex items-center gap-2 pt-1">
              <ColorDot color={newColor} />
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) handleCreate(); }}
                placeholder={t('pms.settings.newLabelNamePlaceholder')}
                className="app-text-body flex-1 border-b border-app-border bg-transparent py-0.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
              />
              <ColorPicker value={newColor} onChange={setNewColor} />
              {newName.trim() && (
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className="text-app-accent hover:opacity-80 disabled:opacity-40"
                  aria-label={t('pms.settings.addLabel')}
                >
                  {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                </button>
              )}
            </div>
          </section>

          {/* Statuses section */}
          <section className="space-y-3">
            <h3 className="app-text-overline text-app-ink/50">{t('pms.settings.workflowStatuses')}</h3>

            {!loading && (
              <div className="space-y-1">
                {statuses.map(ps => (
                  <div key={ps.id} className="flex items-center gap-2 py-1.5 group">
                    {editingStatusId === ps.id ? (
                      <>
                        <ColorDot color={editStatusColor} />
                        <input
                          autoFocus
                          value={editStatusName}
                          onChange={e => setEditStatusName(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') handleSaveEditStatus(); if (e.key === 'Escape') setEditingStatusId(null); }}
                          className="app-text-body flex-1 rounded border border-app-border bg-app-surface-sidebar px-2 py-0.5 text-app-ink focus:border-app-accent focus:outline-none"
                        />
                        <select
                          value={editStatusCategory}
                          onChange={e => setEditStatusCategory(e.target.value)}
                          className="app-text-micro rounded border border-app-border bg-app-surface-sidebar px-1 py-0.5 text-app-ink focus:outline-none"
                        >
                          {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
                        </select>
                        <ColorPicker value={editStatusColor} onChange={setEditStatusColor} />
                        <button onClick={handleSaveEditStatus} className="text-app-accent hover:opacity-80" aria-label={t('pms.settings.saveStatus')}>
                          <Check size={14} />
                        </button>
                      </>
                    ) : (
                      <>
                        <ColorDot color={ps.color} />
                        <span className="app-text-body flex-1 text-app-ink">{ps.name}</span>
                        <span className="app-text-micro uppercase text-app-ink/30">{categoryLabels.get(ps.category) ?? ps.category}</span>
                        <button
                          onClick={() => startEditStatus(ps)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-ink transition-all"
                          aria-label={t('pms.settings.editStatus', { name: ps.name })}
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDeleteStatus(ps.id)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-red-400 transition-all"
                          aria-label={t('pms.settings.deleteStatus', { name: ps.name })}
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Add new status */}
            <div className="space-y-2 pt-1">
              <div className="flex items-center gap-2">
                <ColorDot color={newStatusColor} />
                <input
                  value={newStatusName}
                  onChange={e => setNewStatusName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && newStatusName.trim()) handleCreateStatus(); }}
                  placeholder={t('pms.settings.newStatusNamePlaceholder')}
                  className="app-text-body flex-1 border-b border-app-border bg-transparent py-0.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                />
                <select
                  value={newStatusCategory}
                  onChange={e => setNewStatusCategory(e.target.value)}
                  className="app-text-micro rounded border border-app-border bg-app-surface-sidebar px-1 py-0.5 text-app-ink focus:outline-none"
                >
                  {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{t(o.labelKey)}</option>)}
                </select>
                <ColorPicker value={newStatusColor} onChange={setNewStatusColor} />
                {newStatusName.trim() && (
                  <button
                    onClick={handleCreateStatus}
                    disabled={creatingStatus}
                    className="text-app-accent hover:opacity-80 disabled:opacity-40"
                    aria-label={t('pms.settings.addStatus')}
                  >
                    {creatingStatus ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                  </button>
                )}
              </div>
            </div>
          </section>
        </div>
      </motion.div>
    </>
  );
}

function ColorDot({ color }: { color: string }) {
  return <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: color }} />;
}

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div className="flex gap-0.5">
      {PRESET_COLORS.map(c => (
        <button
          key={c}
          onClick={() => onChange(c)}
          className={`w-3 h-3 rounded-full transition-transform ${value === c ? 'scale-125 ring-1 ring-white/50' : 'hover:scale-110'}`}
          style={{ backgroundColor: c }}
          title={c}
        />
      ))}
    </div>
  );
}
