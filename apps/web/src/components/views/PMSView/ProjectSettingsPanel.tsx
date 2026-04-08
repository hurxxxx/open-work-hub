import { useState, useEffect, useCallback } from 'react';
import { motion } from 'motion/react';
import { X, Plus, Pencil, Trash2, Check, Loader2 } from 'lucide-react';
import { Button, InlineNotice } from '@aidoo/ui';
import { useAuth } from '@/src/domains/auth/auth-provider';
import {
  listProjectLabels,
  createProjectLabel,
  updateLabel,
  deleteLabel,
  listProjectStatuses,
  createProjectStatus,
  updateProjectStatus,
  deleteProjectStatus,
  type PmsLabel,
  type PmsProjectStatus,
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

export function ProjectSettingsPanel({
  projectId,
  onClose,
  onLabelsChanged,
  onStatusesChanged,
}: {
  projectId: string;
  onClose: () => void;
  onLabelsChanged?: (labels: PmsLabel[]) => void;
  onStatusesChanged?: (statuses: PmsProjectStatus[]) => void;
}) {
  const { token } = useAuth();
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
      const [labelRes, statusRes] = await Promise.all([
        listProjectLabels(token, projectId),
        listProjectStatuses(token, projectId),
      ]);
      setLabels(labelRes.items);
      notifyParent(labelRes.items);
      setStatuses(statusRes.items);
      notifyStatusParent(statusRes.items);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '설정을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [notifyParent, notifyStatusParent, projectId, token]);

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

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <motion.div
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed right-0 top-0 bottom-0 z-50 w-80 bg-clickup-bg border-l border-clickup-border shadow-2xl flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-clickup-border shrink-0">
          <h2 className="text-sm font-semibold text-clickup-text">Project Settings</h2>
          <Button variant="ghost" size="icon" onClick={onClose}><X size={16} /></Button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-4 space-y-6">
          {/* Labels section */}
          <section className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-clickup-text/50">Labels</h3>

            {error ? <InlineNotice tone="danger">{error}</InlineNotice> : null}

            {loading ? (
              <div className="flex justify-center py-6"><Loader2 size={18} className="animate-spin text-clickup-text/40" /></div>
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
                          className="flex-1 bg-clickup-sidebar border border-clickup-border rounded px-2 py-0.5 text-sm text-clickup-text focus:outline-none focus:border-clickup-purple"
                        />
                        <ColorPicker value={editColor} onChange={setEditColor} />
                        <button onClick={handleSaveEdit} className="text-clickup-purple hover:opacity-80">
                          <Check size={14} />
                        </button>
                      </>
                    ) : (
                      <>
                        <ColorDot color={label.color} />
                        <span className="flex-1 text-sm text-clickup-text">{label.name}</span>
                        <button
                          onClick={() => startEdit(label)}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-clickup-text transition-all"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDelete(label.id)}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-red-400 transition-all"
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
                className="flex-1 bg-transparent border-b border-clickup-border text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none focus:border-clickup-purple py-0.5 transition-colors"
              />
              <ColorPicker value={newColor} onChange={setNewColor} />
              {newName.trim() && (
                <button
                  onClick={handleCreate}
                  disabled={creating}
                  className="text-clickup-purple hover:opacity-80 disabled:opacity-40"
                >
                  {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                </button>
              )}
            </div>
          </section>

          {/* Statuses section */}
          <section className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-clickup-text/50">Workflow Statuses</h3>

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
                          className="flex-1 bg-clickup-sidebar border border-clickup-border rounded px-2 py-0.5 text-sm text-clickup-text focus:outline-none focus:border-clickup-purple"
                        />
                        <select
                          value={editStatusCategory}
                          onChange={e => setEditStatusCategory(e.target.value)}
                          className="bg-clickup-sidebar border border-clickup-border rounded px-1 py-0.5 text-[10px] text-clickup-text focus:outline-none"
                        >
                          {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                        <ColorPicker value={editStatusColor} onChange={setEditStatusColor} />
                        <button onClick={handleSaveEditStatus} className="text-clickup-purple hover:opacity-80">
                          <Check size={14} />
                        </button>
                      </>
                    ) : (
                      <>
                        <ColorDot color={ps.color} />
                        <span className="flex-1 text-sm text-clickup-text">{ps.name}</span>
                        <span className="text-[9px] text-clickup-text/30 uppercase">{ps.category}</span>
                        <button
                          onClick={() => startEditStatus(ps)}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-clickup-text transition-all"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => handleDeleteStatus(ps.id)}
                          className="opacity-0 group-hover:opacity-100 text-clickup-text/40 hover:text-red-400 transition-all"
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
                  className="flex-1 bg-transparent border-b border-clickup-border text-sm text-clickup-text placeholder:text-clickup-text/40 focus:outline-none focus:border-clickup-purple py-0.5 transition-colors"
                />
                <select
                  value={newStatusCategory}
                  onChange={e => setNewStatusCategory(e.target.value)}
                  className="bg-clickup-sidebar border border-clickup-border rounded px-1 py-0.5 text-[10px] text-clickup-text focus:outline-none"
                >
                  {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                <ColorPicker value={newStatusColor} onChange={setNewStatusColor} />
                {newStatusName.trim() && (
                  <button
                    onClick={handleCreateStatus}
                    disabled={creatingStatus}
                    className="text-clickup-purple hover:opacity-80 disabled:opacity-40"
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
