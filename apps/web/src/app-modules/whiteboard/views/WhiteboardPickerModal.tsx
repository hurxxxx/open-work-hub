import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { Loader2, PencilRuler, Search } from 'lucide-react';

import { useAuth } from '@/src/platform/auth/auth-provider';
import { formatDateTime, normalizeTimeZone } from '@/src/platform/time/time-utils';
import {
  listWhiteboardHub,
  type WhiteboardHubItem,
} from '../api/whiteboard-api';

interface WhiteboardPickerModalProps {
  isOpen: boolean;
  workspaceSlug?: string | null;
  excludeWhiteboardIds?: string[];
  onClose: () => void;
  onPick: (item: WhiteboardHubItem) => Promise<void> | void;
}

export function WhiteboardPickerModal({
  isOpen,
  workspaceSlug,
  excludeWhiteboardIds = [],
  onClose,
  onPick,
}: WhiteboardPickerModalProps) {
  const { token, user } = useAuth();
  const timeZone = normalizeTimeZone(user?.time_zone);
  const [items, setItems] = useState<WhiteboardHubItem[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !token) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    listWhiteboardHub(
      token,
      { view: 'all', sort_by: 'updated_at', sort_dir: 'desc', page_size: 100 },
      workspaceSlug,
    )
      .then((response) => {
        if (cancelled) return;
        setItems(response.items);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message || '화이트보드를 불러올 수 없습니다.');
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token, workspaceSlug]);

  const excludeSet = useMemo(() => new Set(excludeWhiteboardIds), [excludeWhiteboardIds]);
  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((item) => !excludeSet.has(item.id))
      .filter((item) => (q ? item.title.toLowerCase().includes(q) : true))
      .slice(0, 50);
  }, [excludeSet, items, query]);

  async function handlePick(item: WhiteboardHubItem) {
    setSubmittingId(item.id);
    setError(null);
    try {
      await onPick(item);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '화이트보드를 연결할 수 없습니다.');
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Whiteboard 선택"
      description="이미 저장된 Whiteboard를 연결합니다."
      maxWidth="max-w-xl"
      actions={<Button variant="secondary" onClick={onClose}>닫기</Button>}
    >
      <div className="space-y-4 text-app-ink">
        {error ? (
          <div
            role="alert"
            className="app-text-body rounded-md border border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-3 py-2 text-[var(--ui-color-danger)]"
          >
            {error}
          </div>
        ) : null}

        <label className="flex h-9 items-center gap-2 rounded-md border border-app-border bg-app-surface-sidebar px-3 text-app-ink/60">
          <Search size={14} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="제목으로 검색"
            className="app-text-body-sm min-w-0 flex-1 bg-transparent text-app-ink outline-none placeholder:text-app-ink/35"
          />
        </label>

        <div className="max-h-80 overflow-y-auto rounded-md border border-app-border">
          {loading ? (
            <div className="flex h-24 items-center justify-center text-app-ink/40">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="px-4 py-8 text-center app-text-caption text-app-ink/50">
              연결할 Whiteboard가 없습니다.
            </div>
          ) : (
            <ul className="divide-y divide-app-border">
              {filteredItems.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void handlePick(item)}
                    disabled={submittingId !== null}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <PencilRuler size={16} className="shrink-0 text-app-accent" />
                      <div className="min-w-0">
                        <p className="app-text-body line-clamp-1 text-app-ink">{item.title}</p>
                        <p className="app-text-caption text-app-ink/45">
                          {item.location_label} · {formatDateTime(item.updated_at, {
                            day: 'numeric',
                            locale: 'ko-KR',
                            month: 'short',
                            timeZone,
                          })}
                        </p>
                      </div>
                    </div>
                    {submittingId === item.id ? (
                      <Loader2 size={14} className="shrink-0 animate-spin text-app-ink/40" />
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Dialog>
  );
}
