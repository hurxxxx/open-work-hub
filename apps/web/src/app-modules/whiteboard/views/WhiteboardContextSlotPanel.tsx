import { useCallback, useEffect, useState } from 'react';
import { Button } from '@aidoo/ui';
import { Loader2, PencilRuler, Plus, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  attachWhiteboardContextSlot,
  createWhiteboardContextSlot,
  detachWhiteboardContextSlot,
  getWhiteboardContextSlot,
  type WhiteboardDetail,
  type WhiteboardHubItem,
} from '../api/whiteboard-api';
import { WhiteboardEditorSurface } from './WhiteboardEditorSurface';
import { WhiteboardPickerModal } from './WhiteboardPickerModal';

interface WhiteboardContextRef {
  app: string;
  type: string;
  id: string;
}

interface WhiteboardContextSlotPanelProps {
  context: WhiteboardContextRef;
  workspaceSlug?: string | null;
  defaultTitle: string;
  canEditContext: boolean;
  className?: string;
  editorClassName?: string;
}

export function WhiteboardContextSlotPanel({
  context,
  workspaceSlug,
  defaultTitle,
  canEditContext,
  className,
  editorClassName,
}: WhiteboardContextSlotPanelProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const [item, setItem] = useState<WhiteboardDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSlot = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await getWhiteboardContextSlot(token, context, workspaceSlug);
      setItem(response.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.loadSlotFailed'));
      setItem(null);
    } finally {
      setLoading(false);
    }
  }, [context, t, token, workspaceSlug]);

  useEffect(() => {
    void loadSlot();
  }, [loadSlot]);

  async function handleCreate() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createWhiteboardContextSlot(
        token,
        { ...context, title: defaultTitle },
        workspaceSlug,
      );
      setItem(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.createFailed'));
    } finally {
      setBusy(false);
    }
  }

  async function handleAttach(selected: WhiteboardHubItem) {
    if (!token) return;
    const attached = await attachWhiteboardContextSlot(
      token,
      { ...context, whiteboard_id: selected.id },
      workspaceSlug,
    );
    setItem(attached);
  }

  async function handleDetach() {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await detachWhiteboardContextSlot(token, context, workspaceSlug);
      setItem(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('whiteboard.detachFailed'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col rounded-md border border-app-border bg-app-bg', className)}>
      {error ? (
        <div
          role="alert"
          className="app-text-body border-b border-[var(--ui-color-danger)]/30 bg-[var(--ui-color-danger)]/10 px-4 py-2 text-[var(--ui-color-danger)]"
        >
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex min-h-[360px] flex-1 items-center justify-center text-app-ink/40">
          <Loader2 size={22} className="animate-spin" />
        </div>
      ) : item ? (
        <WhiteboardEditorSurface
          key={item.id}
          boardId={item.id}
          workspaceSlug={workspaceSlug}
          showArchive={false}
          showDetach={canEditContext}
          onDetach={handleDetach}
          onBoardUpdated={(updated) => setItem(updated)}
          className={cn('min-h-[560px]', editorClassName)}
        />
      ) : (
        <div className="flex min-h-[360px] flex-1 items-center justify-center px-6 py-10">
          <div className="max-w-sm text-center">
            <PencilRuler size={30} className="mx-auto mb-3 text-app-ink/30" />
            <p className="app-text-title-md text-app-ink">Whiteboard</p>
            <p className="app-text-body-sm mt-2 text-app-ink/55">
              {t('whiteboard.connectedEmpty')}
            </p>
            {canEditContext ? (
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                <Button onClick={() => void handleCreate()} disabled={busy}>
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                  {t('whiteboard.new')}
                </Button>
                <Button variant="secondary" onClick={() => setPickerOpen(true)} disabled={busy}>
                  <Search size={14} />
                  {t('whiteboard.chooseExisting')}
                </Button>
              </div>
            ) : (
              <p className="app-text-caption mt-4 text-app-ink/45">{t('whiteboard.editPermissionHint')}</p>
            )}
          </div>
        </div>
      )}

      <WhiteboardPickerModal
        isOpen={pickerOpen}
        workspaceSlug={workspaceSlug}
        excludeWhiteboardIds={item ? [item.id] : []}
        onClose={() => setPickerOpen(false)}
        onPick={handleAttach}
      />
    </div>
  );
}
