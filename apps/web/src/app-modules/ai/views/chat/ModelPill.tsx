import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { ChevronDown, RefreshCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type {
  AiBackendMode,
  LlmHealthResponse,
  LlmPoolHealthResponse,
} from '../../api/ai-api';

interface ModelPillProps {
  backendMode: AiBackendMode;
  onBackendModeChange: (mode: AiBackendMode) => void;
  health: LlmHealthResponse | null;
  healthError: string | null;
  isCheckingHealth: boolean;
  onRefreshHealth: () => void;
  canRefresh: boolean;
}

const BACKEND_OPTIONS: Array<{
  value: AiBackendMode;
  labelKey: string;
  descriptionKey: string;
}> = [
  { value: 'auto', labelKey: 'ai.model.auto', descriptionKey: 'ai.model.policyRouting' },
  { value: 'local', labelKey: 'ai.model.local', descriptionKey: 'ai.model.localPoolFixed' },
];

function formatPillLabel(
  health: LlmHealthResponse | null,
  mode: AiBackendMode,
  t: (key: string) => string,
): string {
  if (!health) {
    return mode === 'local' ? t('ai.model.localChecking') : t('ai.model.autoChecking');
  }
  if (mode === 'local') {
    return `${health.local.canonical_model} · ${t('ai.model.local')}`;
  }
  return t('ai.message.autoRouting');
}

function formatBackendStatus(
  health: LlmPoolHealthResponse | null | undefined,
  t: (key: string) => string,
): string {
  if (!health) {
    return t('ai.model.notChecked');
  }
  if (health.ready) {
    return t('ai.routing.ready');
  }
  return health.status;
}

interface PanelPosition {
  top: number;
  left: number;
  width: number;
}

// Pure helper so the clamp logic can be unit-tested without jsdom layout.
// Anchors the panel's right edge to the trigger's right edge, then clamps
// `left` within [margin, viewportWidth - width - margin] so the panel can
// never overflow either side of the viewport.
export function computePanelPosition(
  triggerRect: { bottom: number; right: number },
  viewportWidth: number,
  options?: { desiredWidth?: number; margin?: number; offset?: number },
): PanelPosition {
  const { desiredWidth = 320, margin = 8, offset = 8 } = options ?? {};
  const width = Math.max(0, Math.min(desiredWidth, viewportWidth - margin * 2));
  const maxLeft = Math.max(margin, viewportWidth - width - margin);
  const preferredLeft = triggerRect.right - width;
  const left = Math.max(margin, Math.min(maxLeft, preferredLeft));
  return { top: triggerRect.bottom + offset, left, width };
}

export function ModelPill(props: ModelPillProps) {
  const { t } = useTranslation('apps');
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const recomputePosition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    setPosition(computePanelPosition(rect, window.innerWidth));
  }, []);

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
      recomputePosition();
    }
    function onResize() {
      recomputePosition();
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
  }, [open, recomputePosition]);

  const panel =
    open && position && typeof document !== 'undefined'
      ? createPortal(
          <div
            ref={panelRef}
            className="fixed z-50 rounded-xl border border-app-border bg-app-surface p-3 shadow-lg"
            role="dialog"
            style={{
              top: position.top,
              left: position.left,
              width: position.width,
            }}
          >
            <div className="space-y-1 pb-1">
              <div className="app-text-control-sm text-app-ink">{t('ai.model.routingMode')}</div>
              <div className="app-text-micro text-gray-500">
                {t('ai.model.routingModeDescription')}
              </div>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {BACKEND_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  className={`min-h-14 rounded-lg border px-2 py-2 text-left transition-colors ${
                    props.backendMode === option.value
                      ? 'border-app-accent bg-app-bg text-app-ink'
                      : 'border-app-border bg-app-surface text-gray-500 hover:border-app-accent hover:text-app-ink'
                  }`}
                  onClick={() => props.onBackendModeChange(option.value)}
                  type="button"
                >
                  <span className="block app-text-control-sm">{t(option.labelKey)}</span>
                  <span className="block app-text-micro">
                    {t(option.descriptionKey)}
                  </span>
                </button>
              ))}
            </div>
            <div className="mt-3 rounded-lg border border-app-border bg-app-bg px-3 py-1">
              <PoolRow health={props.health?.local} label={t('ai.model.localPool')} />
              <PoolRow health={props.health?.external} label={t('ai.model.externalPool')} />
            </div>
            {props.healthError ? (
              <div className="mt-2 app-text-micro text-red-600 dark:text-red-400">
                {props.healthError}
              </div>
            ) : null}
            <button
              className="app-text-control-sm mt-3 flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-app-border bg-app-surface text-app-ink transition-colors hover:border-app-accent disabled:cursor-not-allowed disabled:opacity-60"
              disabled={!props.canRefresh || props.isCheckingHealth}
              onClick={props.onRefreshHealth}
              type="button"
            >
              <RefreshCcw
                size={14}
                className={props.isCheckingHealth ? 'animate-spin' : ''}
              />
              {t('ai.model.refreshStatus')}
            </button>
          </div>,
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
        <div className="app-text-micro truncate text-gray-500">
          {health?.model ?? t('ai.model.modelChecking')}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${ready ? 'bg-emerald-500' : 'bg-amber-500'}`}
        />
        <span className="app-text-micro text-gray-500">
          {formatBackendStatus(health, t)}
        </span>
      </div>
    </div>
  );
}
