import { ChevronDown, RefreshCcw } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useEffectEvent,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import type {
  AiBackendMode,
  LlmHealthResponse,
  LlmPoolHealthResponse,
} from '../../api/chatbot-api';
import {
  BACKEND_OPTIONS,
  formatBackendStatus,
  formatPillLabel,
  isRefreshDisabled,
  projectBackendOption,
} from './model-pill-model';
import {
  computePanelPosition,
  type PanelPosition,
} from './model-pill-position';

interface ModelPillProps {
  backendMode: AiBackendMode;
  onBackendModeChange: (mode: AiBackendMode) => void;
  health: LlmHealthResponse | null;
  healthError: string | null;
  isCheckingHealth: boolean;
  onRefreshHealth: () => void;
  canRefresh: boolean;
}

export function ModelPill(props: ModelPillProps) {
  const { t } = useTranslation('apps');
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDialogElement | null>(null);

  const recomputePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    setPosition(computePanelPosition(rect, window.innerWidth));
  }, []);
  const recomputePositionEvent = useEffectEvent(recomputePosition);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }
    recomputePosition();
  }, [open, recomputePosition]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onScroll() {
      recomputePositionEvent();
    }
    function onResize() {
      recomputePositionEvent();
    }
    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) {
        return;
      }
      if (panelRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    }
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onResize);
    window.addEventListener('mousedown', onPointerDown);
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('scroll', onScroll, true);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('mousedown', onPointerDown);
      window.removeEventListener('keydown', onKeyDown);
    };
    // `useEffectEvent` callbacks are intentionally omitted from dependencies.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const panel =
    open && position && typeof document !== 'undefined'
      ? createPortal(
          <dialog
            open
            ref={panelRef}
            aria-label={t('ai.model.routingMode')}
            className="m-0 max-h-none max-w-none fixed z-50 rounded-xl border border-app-border bg-app-surface p-3 shadow-lg"
            style={{
              top: position.top,
              left: position.left,
              width: position.width,
            }}
          >
            <div className="space-y-1 pb-1">
              <div className="app-text-control-sm text-app-ink">
                {t('ai.model.routingMode')}
              </div>
              <div className="app-text-micro text-app-ink/55">
                {t('ai.model.routingModeDescription')}
              </div>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {BACKEND_OPTIONS.map((option) => {
                const projected = projectBackendOption(
                  option,
                  props.backendMode,
                  t,
                );
                return (
                  <button
                    key={projected.value}
                    className={`min-h-14 rounded-lg border px-2 py-2 text-left transition-colors ${projected.className}`}
                    onClick={() => props.onBackendModeChange(projected.value)}
                    type="button"
                  >
                    <span className="block app-text-control-sm">
                      {projected.label}
                    </span>
                    <span className="block app-text-micro">
                      {projected.description}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-3 rounded-lg border border-app-border bg-app-bg px-3 py-1">
              <PoolRow
                health={props.health?.local}
                label={t('ai.model.localPool')}
              />
              <PoolRow
                health={props.health?.external}
                label={t('ai.model.externalPool')}
              />
            </div>
            {props.healthError ? (
              <div className="mt-2 app-text-micro text-app-danger-text dark:text-app-danger-text">
                {props.healthError}
              </div>
            ) : null}
            <button
              className="app-text-control-sm mt-3 flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-app-border bg-app-surface text-app-ink transition-colors hover:border-app-accent disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isRefreshDisabled(props)}
              onClick={props.onRefreshHealth}
              type="button"
            >
              <RefreshCcw
                size={14}
                className={props.isCheckingHealth ? 'animate-spin' : ''}
              />
              {t('ai.model.refreshStatus')}
            </button>
          </dialog>,
          document.body,
        )
      : null;

  return (
    <>
      <button
        ref={triggerRef}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="app-text-control-sm flex h-8 max-w-[260px] items-center gap-1.5 rounded-full border border-app-border bg-app-surface px-3 text-app-ink transition-colors hover:border-app-accent"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <span className="truncate">
          {formatPillLabel(props.health, props.backendMode, t)}
        </span>
        <ChevronDown
          size={14}
          className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {panel}
    </>
  );
}

function PoolRow({
  health,
  label,
}: {
  health: LlmPoolHealthResponse | null | undefined;
  label: string;
}) {
  const { t } = useTranslation('apps');
  const ready = Boolean(health?.ready);
  return (
    <div className="flex items-start justify-between gap-3 border-b border-app-border py-2 last:border-b-0">
      <div className="min-w-0">
        <div className="app-text-control-sm text-app-ink">{label}</div>
        <div className="app-text-micro truncate text-app-ink/55">
          {health?.model ?? t('ai.model.modelChecking')}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${ready ? 'bg-app-success' : 'bg-app-warning'}`}
        />
        <span className="app-text-micro text-app-ink/55">
          {formatBackendStatus(health, t)}
        </span>
      </div>
    </div>
  );
}
