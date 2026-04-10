import { useEffect, useMemo, useState } from 'react';
import { Button, Dialog } from '@aidoo/ui';
import { Loader2 } from 'lucide-react';

import { useAuth } from '@/src/domains/auth/auth-provider';
import { listDocsHub, type DocsHubItem } from '@/src/domains/docs/docs-api';

interface DocPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPick: (doc: DocsHubItem) => Promise<void> | void;
  excludeDocIds?: string[];
}

export function DocPickerModal({
  isOpen,
  onClose,
  onPick,
  excludeDocIds = [],
}: DocPickerModalProps) {
  const { token } = useAuth();
  const [items, setItems] = useState<DocsHubItem[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !token) return;
    setQuery('');
    setError(null);
    setSubmittingId(null);
    let cancelled = false;
    setLoading(true);
    listDocsHub(token, { sort_by: 'updated_at', sort_dir: 'desc', page_size: 50 })
      .then((response) => {
        if (cancelled) return;
        setItems(response.items.filter((item) => item.source_type === 'native_doc'));
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message ?? '문서를 불러올 수 없습니다.');
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, token]);

  const excludeSet = useMemo(() => new Set(excludeDocIds), [excludeDocIds]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((item) => !excludeSet.has(item.source_id))
      .filter((item) => (q ? item.title.toLowerCase().includes(q) : true))
      .slice(0, 50);
  }, [items, query, excludeSet]);

  async function handlePick(doc: DocsHubItem) {
    setSubmittingId(doc.source_id);
    setError(null);
    try {
      await onPick(doc);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '문서를 첨부할 수 없습니다.');
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
      title="문서 첨부"
      maxWidth="max-w-xl"
      actions={
        <div className="flex w-full items-center justify-end">
          <Button variant="secondary" onClick={onClose}>닫기</Button>
        </div>
      }
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

        <div className="space-y-1">
          <label className="app-text-control-sm text-app-ink/70">검색</label>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="문서 제목으로 검색"
            className="app-text-body w-full rounded-md border border-app-border bg-app-surface-sidebar px-3 py-2 text-app-ink placeholder:text-app-ink/30 focus:border-app-accent focus:outline-none"
          />
        </div>

        <div className="max-h-72 overflow-y-auto rounded-md border border-app-border">
          {loading ? (
            <div className="flex h-24 items-center justify-center text-app-ink/40">
              <Loader2 size={16} className="animate-spin" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="px-4 py-6 text-center app-text-caption text-app-ink/50">
              표시할 문서가 없습니다. PR1 은 NativeDoc 만 첨부할 수 있습니다.
            </div>
          ) : (
            <ul className="divide-y divide-app-border">
              {filteredItems.map((item) => (
                <li key={item.source_id}>
                  <button
                    type="button"
                    onClick={() => handlePick(item)}
                    disabled={submittingId !== null}
                    className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-app-surface-hover disabled:opacity-50"
                  >
                    <div className="min-w-0">
                      <p className="app-text-body line-clamp-1 text-app-ink">
                        {item.title}
                      </p>
                      <p className="app-text-caption text-app-ink/40">
                        {item.created_by_name} · {new Date(item.updated_at).toLocaleDateString('ko-KR')}
                      </p>
                    </div>
                    {submittingId === item.source_id ? (
                      <Loader2 size={14} className="animate-spin text-app-ink/40" />
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
