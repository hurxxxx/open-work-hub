import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CalendarRange, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface PlannerEventChoicePopoverProps {
  anchor: { x: number; y: number } | null;
  onPickEvent: () => void;
  onPickMeeting: () => void;
  onDismiss: () => void;
}

const POPOVER_WIDTH = 220;
const POPOVER_HEIGHT = 148;
const VIEWPORT_MARGIN = 12;

export function PlannerEventChoicePopover({
  anchor,
  onPickEvent,
  onPickMeeting,
  onDismiss,
}: PlannerEventChoicePopoverProps) {
  const { t } = useTranslation('apps');
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const anchorX = anchor?.x ?? null;
  const anchorY = anchor?.y ?? null;

  useLayoutEffect(() => {
    if (anchorX !== null && anchorY !== null) {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const left = Math.min(
        Math.max(anchorX + 8, VIEWPORT_MARGIN),
        vw - POPOVER_WIDTH - VIEWPORT_MARGIN,
      );
      const top = Math.min(
        Math.max(anchorY + 8, VIEWPORT_MARGIN),
        vh - POPOVER_HEIGHT - VIEWPORT_MARGIN,
      );
      setPosition({ top, left });
      return;
    }
    setPosition({
      top: Math.max((window.innerHeight - POPOVER_HEIGHT) / 2, VIEWPORT_MARGIN),
      left: Math.max((window.innerWidth - POPOVER_WIDTH) / 2, VIEWPORT_MARGIN),
    });
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
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t('planner.createEventOrMeeting')}
      style={{
        position: 'fixed',
        top: position.top,
        left: position.left,
        width: POPOVER_WIDTH,
      }}
      className="z-50 rounded-lg border border-app-border bg-app-surface py-1 shadow-xl"
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
    </div>
  );
}
