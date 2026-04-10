import { useState, useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import { X, Plus, Pencil, Trash2, Check, Loader2 } from 'lucide-react';
import { Button, InlineNotice, Select } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  addSpaceMember,
  listProjectLabels,
  listPmsUsers,
  createProjectLabel,
  updateLabel,
  deleteLabel,
  listSpaceMembers,
  listProjectStatuses,
  createProjectStatus,
  updateProjectStatus,
  deleteProjectStatus,
  updateSpaceMemberRole,
  removeSpaceMember,
  type PmsLabel,
  type PmsSpaceMember,
  type PmsProjectStatus,
  type PmsUserSummary,
} from '@/src/domains/pms/pms-api';

const PRESET_COLORS = [
  '#b45309', '#1d4ed8', '#0f766e', '#7c3aed', '#dc2626',
  '#16a34a', '#ca8a04', '#0284c7', '#9333ea', '#e11d48',
];

const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: 'backlog', label: 'Backlog' },
  { value: 'active', label: 'Active' },
  { value: 'done', label: 'Done' },
  { value: 'canceled', label: 'Canceled' },
];

const ROLE_OPTIONS = [
  { value: 'owner', label: 'Owner' },
  { value: 'admin', label: 'Admin' },
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
];

export function ProjectSettingsPanel({
  projectId,
  teamId,
  onClose,
  onLabelsChanged,
  onStatusesChanged,
}: {
  projectId: string;
  teamId: string | null;
  onClose: () => void;
  onLabelsChanged?: (labels: PmsLabel[]) => void;
  onStatusesChanged?: (statuses: PmsProjectStatus[]) => void;
}) {
  const { token } = useAuth();
  const [members, setMembers] = useState<PmsSpaceMember[]>([]);
  const [availableUsers, setAvailableUsers] = useState<PmsUserSummary[]>([]);
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [statuses, setStatuses] = useState<PmsProjectStatus[]>([]);
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

  const notifyParent = useCallback((updated: PmsLabel[]) => {
    onLabelsChanged?.(updated);
  }, [onLabelsChanged]);

  const notifyStatusParent = useCallback((updated: PmsProjectStatus[]) => {
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
        listProjectLabels(token, projectId),
        listProjectStatuses(token, projectId),
      ]);
      setMembers(memberRes.items);
      setAvailableUsers(userItems);
      setLabels(labelRes.items);
      notifyParent(labelRes.items);
      setStatuses(statusRes.items);
      notifyStatusParent(statusRes.items);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '설정을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [notifyParent, notifyStatusParent, projectId, teamId, token]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const handleCreate = useCallback(async () => {
    if (!token || !newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const label = await createProjectLabel(token, projectId, { name: newName.trim(), color: newColor });
      const updated = [...labels, label];
      setLabels(updated);
      notifyParent(updated);
      setNewName('');
      setNewColor(PRESET_COLORS[0]);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '라벨을 생성하지 못했습니다.');
    } finally {
      setCreating(false);
    }
  }, [token, projectId, newName, newColor, labels, notifyParent]);

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
      setError(caughtError instanceof Error ? caughtError.message : '라벨을 수정하지 못했습니다.');
    }
  }, [token, editingId, editName, editColor, labels, notifyParent]);

  const handleDelete = useCallback(async (labelId: string) => {
    if (!token) return;
    setError(null);
    try {
      await deleteLabel(token, labelId);
      const updated = labels.filter(l => l.id !== labelId);
      setLabels(updated);
      notifyParent(updated);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '라벨을 삭제하지 못했습니다.');
    }
  }, [token, labels, notifyParent]);

  // ── Status handlers ──
  const handleCreateStatus = useCallback(async () => {
    if (!token || !newStatusName.trim()) return;
    setCreatingStatus(true);
    setError(null);
    try {
      const ps = await createProjectStatus(token, projectId, {
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
      setError(caughtError instanceof Error ? caughtError.message : '상태를 생성하지 못했습니다.');
    } finally {
      setCreatingStatus(false);
    }
  }, [token, projectId, newStatusName, newStatusColor, newStatusCategory, statuses, notifyStatusParent]);

  const startEditStatus = (ps: PmsProjectStatus) => {
    setEditingStatusId(ps.id);
    setEditStatusName(ps.name);
    setEditStatusColor(ps.color);
    setEditStatusCategory(ps.category);
  };

  const handleSaveEditStatus = useCallback(async () => {
    if (!token || !editingStatusId || !editStatusName.trim()) return;
    setError(null);
    try {
      const updated = await updateProjectStatus(token, editingStatusId, {
        name: editStatusName.trim(),
        color: editStatusColor,
        category: editStatusCategory,
      });
      const next = statuses.map(s => s.id === editingStatusId ? updated : s);
      setStatuses(next);
      notifyStatusParent(next);
      setEditingStatusId(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '상태를 수정하지 못했습니다.');
    }
  }, [token, editingStatusId, editStatusName, editStatusColor, editStatusCategory, statuses, notifyStatusParent]);

  const handleDeleteStatus = useCallback(async (statusId: string) => {
    if (!token) return;
    setError(null);
    try {
      await deleteProjectStatus(token, statusId);
      const updated = statuses.filter(s => s.id !== statusId);
      setStatuses(updated);
      notifyStatusParent(updated);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '상태를 삭제하지 못했습니다.');
    }
  }, [token, statuses, notifyStatusParent]);

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
      setError(caughtError instanceof Error ? caughtError.message : '멤버를 추가하지 못했습니다.');
    } finally {
      setAddingMember(false);
    }
  }, [selectedRole, selectedUserId, teamId, token]);

  const handleRoleChange = useCallback(async (userId: string, role: string) => {
    if (!token || !teamId) return;
    setError(null);
    try {
      const updatedMember = await updateSpaceMemberRole(token, teamId, userId, role);
      setMembers((current) => current.map((member) => (
        member.user_id === userId ? updatedMember : member
      )));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '멤버 역할을 변경하지 못했습니다.');
    }
  }, [teamId, token]);

  const handleRemoveMember = useCallback(async (userId: string) => {
    if (!token || !teamId) return;
    setError(null);
    try {
      await removeSpaceMember(token, teamId, userId);
      setMembers((current) => current.filter((member) => member.user_id !== userId));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '멤버를 제거하지 못했습니다.');
    }
  }, [teamId, token]);

  const memberCandidateOptions = [
    { value: '__none__', label: 'Add member by email' },
    ...availableUsers
      .filter((user) => !members.some((member) => member.user_id === user.id))
      .map((user) => ({
        value: user.id,
        label: `${user.full_name} (${user.email})`,
      })),
  ];

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
          <h2 className="app-text-title-md text-app-ink">List Settings</h2>
          <Button variant="ghost" size="icon" onClick={onClose}><X size={16} /></Button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-4 space-y-6">
          <section className="space-y-3">
            <h3 className="app-text-overline text-app-ink/50">Members</h3>

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
                    {ROLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  <Button
                    disabled={selectedUserId === '__none__' || addingMember}
                    onClick={() => { void handleAddMember(); }}
                    variant="secondary"
                  >
                    Add
                  </Button>
                </div>
              </div>
            ) : null}

            {loading ? (
              <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-app-ink/40" /></div>
            ) : (
              <div className="space-y-2">
                {members.map((member) => (
                  <div key={member.user_id} className="rounded-lg border border-app-border bg-app-surface-sidebar px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="app-text-body truncate font-medium text-app-ink">{member.full_name}</div>
                        <div className="app-text-caption truncate text-app-ink/45">{member.email}</div>
                      </div>
                      <button
                        onClick={() => { void handleRemoveMember(member.user_id); }}
                        className="text-app-ink/35 hover:text-red-400 transition-colors"
                        title="Remove member"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <div className="app-text-micro text-app-ink/35">
                        Joined {new Date(member.joined_at).toLocaleDateString()}
                      </div>
                      <select
                        value={member.role}
                        onChange={(event) => { void handleRoleChange(member.user_id, event.target.value); }}
                        className="app-text-caption rounded border border-app-border bg-app-bg px-2 py-1 text-app-ink focus:outline-none"
                      >
                        {ROLE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Labels section */}
          <section className="space-y-3">
            <h3 className="app-text-overline text-app-ink/50">Labels</h3>

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
                        <button onClick={handleSaveEdit} className="text-app-accent hover:opacity-80">
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
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDelete(label.id)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-red-400 transition-all"
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
                placeholder="New label name..."
                className="app-text-body flex-1 border-b border-app-border bg-transparent py-0.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
              />
              <ColorPicker value={newColor} onChange={setNewColor} />
              {newName.trim() && (
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className="text-app-accent hover:opacity-80 disabled:opacity-40"
                >
                  {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                </button>
              )}
            </div>
          </section>

          {/* Statuses section */}
          <section className="space-y-3">
            <h3 className="app-text-overline text-app-ink/50">Workflow Statuses</h3>

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
                          {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                        <ColorPicker value={editStatusColor} onChange={setEditStatusColor} />
                        <button onClick={handleSaveEditStatus} className="text-app-accent hover:opacity-80">
                          <Check size={14} />
                        </button>
                      </>
                    ) : (
                      <>
                        <ColorDot color={ps.color} />
                        <span className="app-text-body flex-1 text-app-ink">{ps.name}</span>
                        <span className="app-text-micro uppercase text-app-ink/30">{ps.category}</span>
                        <button
                          onClick={() => startEditStatus(ps)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-app-ink transition-all"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDeleteStatus(ps.id)}
                          className="opacity-0 group-hover:opacity-100 text-app-ink/40 hover:text-red-400 transition-all"
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
                  placeholder="New status name..."
                  className="app-text-body flex-1 border-b border-app-border bg-transparent py-0.5 text-app-ink placeholder:text-app-ink/40 transition-colors focus:border-app-accent focus:outline-none"
                />
                <select
                  value={newStatusCategory}
                  onChange={e => setNewStatusCategory(e.target.value)}
                  className="app-text-micro rounded border border-app-border bg-app-surface-sidebar px-1 py-0.5 text-app-ink focus:outline-none"
                >
                  {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                <ColorPicker value={newStatusColor} onChange={setNewStatusColor} />
                {newStatusName.trim() && (
                  <button
                    onClick={handleCreateStatus}
                    disabled={creatingStatus}
                    className="text-app-accent hover:opacity-80 disabled:opacity-40"
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
