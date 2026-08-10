import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CalendarRange, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  resolvePlannerEventChoicePopoverPlacement,
  type PlannerEventChoicePopoverPlacement,
} from './planner-event-choice-popover-model';

interface PlannerEventChoicePopoverProps {
  anchor: { x: number; y: number } | null;
  onPickEvent: () => void;
  onPickMeeting: () => void;
  onDismiss: () => void;
}

export function PlannerEventChoicePopover({
  anchor,
  onPickEvent,
  onPickMeeting,
  onDismiss,
}: PlannerEventChoicePopoverProps) {
  const { t } = useTranslation('apps');
  const panelRef = useRef<HTMLDialogElement | null>(null);
  const [position, setPosition] = useState<PlannerEventChoicePopoverPlacement | null>(null);
  const anchorX = anchor?.x ?? null;
  const anchorY = anchor?.y ?? null;

  useLayoutEffect(() => {
    setPosition(resolvePlannerEventChoicePopoverPlacement({
      anchor: anchorX !== null && anchorY !== null
        ? { x: anchorX, y: anchorY }
        : null,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
      },
    }));
  }, [anchorX, anchorY]);

  useEffect(() => {
    function onMouseDown(event: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        onDismiss();
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onDismiss();
    }
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onDismiss]);

  if (!position) return null;

  return (
    <dialog
      open
      ref={panelRef}
      aria-label={t('planner.createEventOrMeeting')}
      style={{
        position: 'fixed',
        top: position.top,
        left: position.left,
        width: position.width,
      }}
      className="z-50 m-0 max-w-none rounded-lg border border-app-border bg-app-surface py-1 shadow-xl"
    >
      <div className="app-text-overline px-3 pt-1.5 pb-1 text-app-ink/45">{t('planner.create')}</div>
      <button
        type="button"
        onClick={onPickEvent}
        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
      >
        <CalendarRange size={14} className="text-app-ink/55" />
        <span>{t('planner.event')}</span>
      </button>
      <button
        type="button"
        onClick={onPickMeeting}
        className="app-text-control-sm flex w-full items-center gap-2 px-3 py-2 text-left text-app-ink transition-colors hover:bg-app-surface-hover"
      >
        <Users size={14} className="text-app-ink/55" />
        <span>{t('planner.meeting')}</span>
      </button>
    </dialog>
  );
}
