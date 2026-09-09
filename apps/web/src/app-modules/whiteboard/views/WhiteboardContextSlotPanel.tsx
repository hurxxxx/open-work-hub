import {
  Button,
  InlineNotice,
  useConfirm,
  useFeedback,
} from '@open-work-hub/ui';
import { Loader2, PencilRuler, Plus, Search } from 'lucide-react';
import { useCallback, useEffect, useReducer, useRef } from 'react';
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

  defaultTitle: string;
  canEditContext: boolean;
  className?: string;
  editorClassName?: string;
}

function WhiteboardContextSlotPanelContent({
  context,
  defaultTitle,
  canEditContext,
  className,
  editorClassName,
}: WhiteboardContextSlotPanelProps) {
  const { t } = useTranslation('apps');
  const { token } = useAuth();
  const { confirm, confirmDialog } = useConfirm();
  const feedback = useFeedback();
  const active = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const [state, dispatch] = useReducer(
    whiteboardContextSlotPanelReducer,
    INITIAL_WHITEBOARD_CONTEXT_SLOT_PANEL_STATE,
  );

  const loadSlot = useCallback(async () => {
    if (!token) return;
    dispatch({ type: 'load-started' });
    try {
      const response = await getWhiteboardContextSlot(token, context);
      if (!active.current) return;
      dispatch({ type: 'load-succeeded', item: response.item });
    } catch (err) {
      if (!active.current) return;
      dispatch({
        type: 'load-failed',
        error:
          err instanceof Error ? err.message : t('whiteboard.loadSlotFailed'),
      });
    }
  }, [context, t, token]);

  useEffect(() => {
    void loadSlot();
  }, [loadSlot]);

  function confirmPublication() {
    return confirm({
      title: t('shell:contentPublication.title'),
      description: t('shell:contentPublication.confirm'),
      confirmLabel: t('common:actions.confirm'),
      cancelLabel: t('common:actions.cancel'),
    });
  }

  async function handleCreate() {
    if (!token || !canEditContext || state.busy) return;
    dispatch({ type: 'create-started' });
    try {
      const acknowledged = await confirmPublication();
      if (!active.current) return;
      if (!acknowledged) {
        dispatch({ type: 'operation-cancelled' });
        return;
      }
      const created = await createWhiteboardContextSlot(
        token,
        buildWhiteboardContextSlotCreatePayload(
          context,
          defaultTitle,
          acknowledged,
        ),
      );
      if (!active.current) return;
      dispatch({ type: 'create-succeeded', item: created });
    } catch (err) {
      if (!active.current) return;
      dispatch({ type: 'operation-cancelled' });
      feedback.error(
        err instanceof Error ? err.message : t('whiteboard.createFailed'),
      );
    }
  }

  async function handleAttach(selected: WhiteboardHubItem) {
    if (!token || !canEditContext || state.busy) return false;
    dispatch({ type: 'attach-started' });
    try {
      const acknowledged =
        selected.ownership_kind === 'personal'
          ? await confirmPublication()
          : false;
      if (
        !active.current ||
        (selected.ownership_kind === 'personal' && !acknowledged)
      )
        return false;
      const attached = await attachWhiteboardContextSlot(
        token,
        buildWhiteboardContextSlotAttachPayload(
          context,
          selected.id,
          acknowledged,
        ),
      );
      if (!active.current) return false;
      dispatch({ type: 'attach-succeeded', item: attached });
    } finally {
      if (active.current) dispatch({ type: 'operation-cancelled' });
    }
  }

  async function handleDetach() {
    if (!token || !canEditContext || state.busy) return;
    dispatch({ type: 'detach-started' });
    try {
      await detachWhiteboardContextSlot(token, context);
      if (!active.current) return;
      dispatch({ type: 'detach-succeeded' });
    } catch (err) {
      if (!active.current) return;
      dispatch({ type: 'operation-cancelled' });
      feedback.error(
        err instanceof Error ? err.message : t('whiteboard.detachFailed'),
      );
    }
  }

  return (
    <div
      className={cn(
        'flex min-h-0 flex-1 flex-col rounded-md border border-app-border bg-app-bg',
        className,
      )}
    >
      {confirmDialog}
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
        excludeWhiteboardIds={getWhiteboardContextSlotExcludeIds(state.item)}
        onClose={() => dispatch({ type: 'picker-closed' })}
        onPick={handleAttach}
      />
    </div>
  );
}

export function WhiteboardContextSlotPanel(
  props: WhiteboardContextSlotPanelProps,
) {
  const { token } = useAuth();
  return (
    <WhiteboardContextSlotPanelContent
      key={JSON.stringify([
        token,
        props.context.app,
        props.context.type,
        props.context.id,
        props.canEditContext,
      ])}
      {...props}
    />
  );
}
