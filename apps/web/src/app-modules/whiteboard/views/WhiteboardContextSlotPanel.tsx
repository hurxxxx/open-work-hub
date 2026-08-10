import { useCallback, useEffect, useReducer } from 'react';
import { Button, InlineNotice } from '@ai-do/ui';
import { Loader2, PencilRuler, Plus, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/src/lib/utils';
import { useAuth } from '@/src/platform/auth/auth-provider';
import {
  attachWhiteboardContextSlot,
  createWhiteboardContextSlot,
  detachWhiteboardContextSlot,
  getWhiteboardContextSlot,
  type WhiteboardHubItem,
} from '../api/whiteboard-api';
import { WhiteboardEditorSurface } from './WhiteboardEditorSurface';
import { WhiteboardPickerModal } from './WhiteboardPickerModal';
import {
  INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE,
  buildWhiteboardContextSlotAttachPayload,
  buildWhiteboardContextSlotCreatePayload,
  getWhiteboardContextSlotExcludeIds,
  whiteboardContextSlotPanelReducer,
  type WhiteboardContextRef,
} from './whiteboard-context-slot-panel-model';

export type { WhiteboardContextRef } from './whiteboard-context-slot-panel-model';

export interface WhiteboardContextSlotPanelProps {
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
  const [state, dispatch] = useReducer(
    whiteboardContextSlotPanelReducer,
    INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE,
  );

  const loadSlot = useCallback(async () => {
    if (!token) return;
    dispatch({ type: 'load-started' });
    try {
      const response = await getWhiteboardContextSlot(
        token,
        context,
        workspaceSlug,
      );
      dispatch({ type: 'load-succeeded', item: response.item });
    } catch (err) {
      dispatch({
        type: 'load-failed',
        error:
          err instanceof Error ? err.message : t('whiteboard.loadSlotFailed'),
      });
    }
  }, [context, t, token, workspaceSlug]);

  useEffect(() => {
    void loadSlot();
  }, [loadSlot]);

  async function handleCreate() {
    if (!token) return;
    dispatch({ type: 'create-started' });
    try {
      const created = await createWhiteboardContextSlot(
        token,
        buildWhiteboardContextSlotCreatePayload(context, defaultTitle),
        workspaceSlug,
      );
      dispatch({ type: 'create-succeeded', item: created });
    } catch (err) {
      dispatch({
        type: 'create-failed',
        error:
          err instanceof Error ? err.message : t('whiteboard.createFailed'),
      });
    }
  }

  async function handleAttach(selected: WhiteboardHubItem) {
    if (!token) return;
    const attached = await attachWhiteboardContextSlot(
      token,
      buildWhiteboardContextSlotAttachPayload(context, selected.id),
      workspaceSlug,
    );
    dispatch({ type: 'attach-succeeded', item: attached });
  }

  async function handleDetach() {
    if (!token) return;
    dispatch({ type: 'detach-started' });
    try {
      await detachWhiteboardContextSlot(token, context, workspaceSlug);
      dispatch({ type: 'detach-succeeded' });
    } catch (err) {
      dispatch({
        type: 'detach-failed',
        error:
          err instanceof Error ? err.message : t('whiteboard.detachFailed'),
      });
    }
  }

  return (
    <div
      className={cn(
        'flex min-h-0 flex-1 flex-col rounded-md border border-app-border bg-app-bg',
        className,
      )}
    >
      {state.error ? (
        <InlineNotice
          role="alert"
          className="rounded-none border-x-0 border-t-0 px-4 app-text-body"
          tone="danger"
        >
          {state.error}
        </InlineNotice>
      ) : null}

      {state.loading ? (
        <div className="flex min-h-[360px] flex-1 items-center justify-center text-app-ink/40">
          <Loader2 size={22} className="animate-spin" />
        </div>
      ) : state.item ? (
        <WhiteboardEditorSurface
          key={state.item.id}
          boardId={state.item.id}
          workspaceSlug={workspaceSlug}
          showArchive={false}
          showDetach={canEditContext}
          onDetach={handleDetach}
          onBoardUpdated={(updated) =>
            dispatch({ type: 'update-succeeded', item: updated })
          }
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
                <Button
                  onClick={() => void handleCreate()}
                  disabled={state.busy}
                >
                  {state.busy ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Plus size={14} />
                  )}
                  {t('whiteboard.new')}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => dispatch({ type: 'picker-opened' })}
                  disabled={state.busy}
                >
                  <Search size={14} />
                  {t('whiteboard.chooseExisting')}
                </Button>
              </div>
            ) : (
              <p className="app-text-caption mt-4 text-app-ink/45">
                {t('whiteboard.editPermissionHint')}
              </p>
            )}
          </div>
        </div>
      )}

      <WhiteboardPickerModal
        isOpen={state.pickerOpen}
        workspaceSlug={workspaceSlug}
        excludeWhiteboardIds={getWhiteboardContextSlotExcludeIds(state.item)}
        onClose={() => dispatch({ type: 'picker-closed' })}
        onPick={handleAttach}
      />
    </div>
  );
}
