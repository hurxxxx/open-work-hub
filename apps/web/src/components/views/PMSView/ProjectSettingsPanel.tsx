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
  type PmsLabel,
} from '@/src/domains/pms/pms-api';

const PRESET_COLORS = [
  '#b45309', '#1d4ed8', '#0f766e', '#7c3aed', '#dc2626',
  '#16a34a', '#ca8a04', '#0284c7', '#9333ea', '#e11d48',
];

export function ProjectSettingsPanel({
  projectId,
  onClose,
  onLabelsChanged,
}: {
  projectId: string;
  onClose: () => void;
  onLabelsChanged?: (labels: PmsLabel[]) => void;
}) {
  const { token } = useAuth();
  const [labels, setLabels] = useState<PmsLabel[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState(PRESET_COLORS[0]);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState('');
  const [error, setError] = useState<string | null>(null);

  const notifyParent = useCallback((updated: PmsLabel[]) => {
    onLabelsChanged?.(updated);
  }, [onLabelsChanged]);

  const loadLabels = useCallback(async () => {
    if (!token) return;

    setLoading(true);
    setError(null);
    try {
      const res = await listProjectLabels(token, projectId);
      setLabels(res.items);
      notifyParent(res.items);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : '라벨을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  }, [notifyParent, projectId, token]);

  useEffect(() => {
    void loadLabels();
  }, [loadLabels]);

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
