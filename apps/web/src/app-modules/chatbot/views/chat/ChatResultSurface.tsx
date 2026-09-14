import { DetailDrawer, useFeedback } from '@open-work-hub/ui';
import {
  Maximize2,
  Minimize2,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { useTranslation } from 'react-i18next';

const narrowQuery = '(max-width: 1023px)';
function subscribeViewport(listener: () => void) {
  const query = window.matchMedia(narrowQuery);
  query.addEventListener('change', listener);
  return () => query.removeEventListener('change', listener);
}
function isNarrow() {
  return window.matchMedia(narrowQuery).matches;
}

export function ChatResultSurface({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation('apps');
  const feedback = useFeedback();
  const narrow = useSyncExternalStore(subscribeViewport, isNarrow, () => false);
  const panelRef = useRef<HTMLElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    const changed = () =>
      setFullscreen(
        document.fullscreenElement === panelRef.current && !!panelRef.current,
      );
    document.addEventListener('fullscreenchange', changed);
    return () => document.removeEventListener('fullscreenchange', changed);
  }, []);
  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement === panelRef.current)
        await document.exitFullscreen();
      else await panelRef.current?.requestFullscreen();
    } catch {
      feedback.error(t('ai.artifacts.fullscreenFailed'));
    }
  };
  useLayoutEffect(() => {
    const trigger = document.activeElement;
    const panel = panelRef.current;
    panel?.focus();
    return () => {
      if (
        trigger instanceof HTMLElement &&
        trigger.isConnected &&
        panel?.contains(document.activeElement)
      )
        trigger.focus();
    };
  }, [narrow]);
  if (narrow) {
    return (
      <DetailDrawer
        open
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        title={title}
        description={t('ai.artifacts.previewDescription')}
        closeLabel={t('ai.artifacts.closePanel')}
        embedded
        contentClassName="!w-full !max-w-full border-app-border bg-app-surface"
      >
        <div className="flex h-full min-h-0 flex-col">{children}</div>
      </DetailDrawer>
    );
  }
  return (
    <aside
      ref={panelRef}
      tabIndex={-1}
      aria-label={title}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !document.fullscreenElement) {
          event.stopPropagation();
          onClose();
        }
      }}
      data-expanded={expanded}
      className={`flex min-h-0 min-w-80 shrink-0 flex-col border-l border-app-border bg-app-surface outline-none [&:fullscreen]:!h-screen [&:fullscreen]:!w-screen [&:fullscreen]:!max-w-none ${expanded ? 'w-[70%] max-w-none' : 'w-[45%] max-w-[960px]'}`}
    >
      <div className="flex shrink-0 items-center justify-end gap-1 border-b border-app-border px-3 py-1 text-app-ink/65">
        <button
          type="button"
          disabled={fullscreen}
          aria-label={t(
            expanded ? 'ai.artifacts.restoreWidth' : 'ai.artifacts.expandWidth',
          )}
          aria-pressed={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="rounded p-2 hover:bg-app-surface-hover disabled:opacity-40"
        >
          {expanded ? (
            <PanelRightClose size={16} />
          ) : (
            <PanelRightOpen size={16} />
          )}
        </button>
        <button
          type="button"
          aria-label={t(
            fullscreen
              ? 'ai.artifacts.exitFullscreen'
              : 'ai.artifacts.enterFullscreen',
          )}
          onClick={() => void toggleFullscreen()}
          className="rounded p-2 hover:bg-app-surface-hover"
        >
          {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
      </div>
      {children}
    </aside>
  );
}
