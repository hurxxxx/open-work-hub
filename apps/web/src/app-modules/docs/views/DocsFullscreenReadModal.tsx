import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent,
  type WheelEvent,
} from 'react';
import {
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Eraser,
  FileCode2,
  FileText,
  Maximize2,
  MousePointer2,
  PenLine,
  RotateCcw,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BlockViewer, type BlockContent } from '@open-work-hub/ui';

import { cn } from '@/src/lib/utils';
import {
  type DocsContentFormat,
  type DocsHubItem,
  type DocsPageItem,
} from '../api/docs-api';
import { DocsHtmlFrame } from './docs-html-renderers';
import {
  DOCS_HTML_ZOOM_MAX,
  DOCS_HTML_ZOOM_MIN,
  DOCS_HTML_ZOOM_STEP,
  buildDocsReadModeProjection,
  clampDocsHtmlZoom,
  formatDocsReadPagePosition,
} from './docs-view-model';

type ReadTool = 'cursor' | 'laser' | 'pen';

const DOCS_LASER_COLOR_VAR = '--ui-color-docs-laser';

interface LaserSegment {
  id: number;
  pageId: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
}

export interface DocsFullscreenReadModalProps {
  doc: DocsHubItem;
  pages: DocsPageItem[];
  selectedPageId: string | null;
  onSelectPage: (pageId: string | null) => void;
  onClose: () => void;
  resolveFileUrl?: (url: string) => Promise<string>;
}

function formatBadgeLabel(
  format: DocsContentFormat,
  blockLabel: string,
  htmlLabel: string,
) {
  return format === 'html' ? htmlLabel : blockLabel;
}

function getCanvasPoint(event: PointerEvent<HTMLCanvasElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

export function DocsFullscreenReadModal({
  doc,
  pages,
  selectedPageId,
  onSelectPage,
  onClose,
  resolveFileUrl,
}: DocsFullscreenReadModalProps) {
  return useDocsFullscreenReadModalElement({
    doc,
    pages,
    selectedPageId,
    onSelectPage,
    onClose,
    resolveFileUrl,
  });
}

function useDocsFullscreenReadModalElement({
  doc,
  pages,
  selectedPageId,
  onSelectPage,
  onClose,
  resolveFileUrl,
}: DocsFullscreenReadModalProps) {
  const { t } = useTranslation(['apps', 'common']);
  const { activeFormat, activeIndex, activePage, flatPages } = useMemo(
    () => buildDocsReadModeProjection({ pages, selectedPageId }),
    [pages, selectedPageId],
  );
  const activeLabel = formatBadgeLabel(
    activeFormat,
    t('apps:docs.contentFormat.block'),
    t('apps:docs.contentFormat.html'),
  );

  const [tool, setTool] = useState<ReadTool>('cursor');
  const [htmlZoom, setHtmlZoom] = useState(1);
  const [laserPoint, setLaserPoint] = useState<
    ({ pageId: string } & { x: number; y: number }) | null
  >(null);
  const [laserSegments, setLaserSegments] = useState<LaserSegment[]>([]);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const htmlFrameRef = useRef<HTMLIFrameElement>(null);
  const readViewportRef = useRef<HTMLDivElement>(null);
  const drawingRef = useRef(false);
  const laserDrawingRef = useRef(false);
  const laserSegmentIdRef = useRef(0);
  const laserSegmentTimeoutsRef = useRef<number[]>([]);
  const lastLaserPointRef = useRef<{ x: number; y: number } | null>(null);
  const lastPointRef = useRef<{ x: number; y: number } | null>(null);

  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = readDocsCssVariable(DOCS_LASER_COLOR_VAR, 'red');
    ctx.lineWidth = 3;
  }, []);

  const clearCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }, []);

  const clearLaserSegments = useCallback(() => {
    setLaserSegments([]);
    for (const timeoutId of laserSegmentTimeoutsRef.current) {
      window.clearTimeout(timeoutId);
    }
    laserSegmentTimeoutsRef.current = [];
  }, []);

  const clearPresentationMarks = useCallback(() => {
    clearCanvas();
    clearLaserSegments();
  }, [clearCanvas, clearLaserSegments]);

  const adjustHtmlZoom = useCallback((delta: number) => {
    setHtmlZoom((current) => clampDocsHtmlZoom(current + delta));
  }, []);

  const addLaserSegment = useCallback(
    (from: { x: number; y: number }, to: { x: number; y: number }) => {
      if (!activePage) return;
      const id = laserSegmentIdRef.current + 1;
      laserSegmentIdRef.current = id;
      setLaserSegments((current) => [
        ...current.slice(-96),
        { id, pageId: activePage.id, from, to },
      ]);
      const timeoutId = window.setTimeout(() => {
        setLaserSegments((current) =>
          current.filter((segment) => segment.id !== id),
        );
      }, 900);
      laserSegmentTimeoutsRef.current.push(timeoutId);
    },
    [activePage],
  );

  const selectPageByIndex = useCallback(
    (index: number) => {
      const nextPage = flatPages[index]?.page ?? null;
      if (!nextPage) return;
      onSelectPage(nextPage.id);
      setLaserPoint(null);
      clearLaserSegments();
      window.setTimeout(() => {
        clearCanvas();
        resizeCanvas();
      }, 0);
    },
    [clearCanvas, clearLaserSegments, flatPages, onSelectPage, resizeCanvas],
  );

  useEffect(() => {
    resizeCanvas();
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(resizeCanvas);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [activePage?.id, resizeCanvas]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        selectPageByIndex(Math.max(0, activeIndex - 1));
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        selectPageByIndex(Math.min(flatPages.length - 1, activeIndex + 1));
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeIndex, flatPages.length, onClose, selectPageByIndex]);

  useEffect(
    () => () => {
      for (const timeoutId of laserSegmentTimeoutsRef.current) {
        window.clearTimeout(timeoutId);
      }
    },
    [],
  );

  if (!activePage) {
    return null;
  }

  const htmlZoomPercent = `${Math.round(htmlZoom * 100)}%`;
  const visibleLaserPoint =
    laserPoint?.pageId === activePage.id ? laserPoint : null;
  const visibleLaserSegments = laserSegments.filter(
    (segment) => segment.pageId === activePage.id,
  );

  const drawTo = (point: { x: number; y: number }) => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    const lastPoint = lastPointRef.current;
    if (!ctx || !lastPoint) return;
    ctx.beginPath();
    ctx.moveTo(lastPoint.x, lastPoint.y);
    ctx.lineTo(point.x, point.y);
    ctx.stroke();
    lastPointRef.current = point;
  };

  const handlePointerDown = (event: PointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = getCanvasPoint(event);
    if (tool === 'laser') {
      laserDrawingRef.current = true;
      lastLaserPointRef.current = point;
      setLaserPoint({ ...point, pageId: activePage.id });
      return;
    }
    if (tool !== 'pen') return;
    drawingRef.current = true;
    lastPointRef.current = point;
  };

  const handlePointerMove = (event: PointerEvent<HTMLCanvasElement>) => {
    const point = getCanvasPoint(event);
    if (tool === 'laser') {
      setLaserPoint({ ...point, pageId: activePage.id });
      if (laserDrawingRef.current) {
        const from = lastLaserPointRef.current;
        if (from) {
          const distance = Math.hypot(point.x - from.x, point.y - from.y);
          if (distance >= 3) {
            addLaserSegment(from, point);
            lastLaserPointRef.current = point;
          }
        }
      }
      return;
    }
    if (tool === 'pen' && drawingRef.current) {
      drawTo(point);
    }
  };

  const stopDrawing = (event: PointerEvent<HTMLCanvasElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drawingRef.current = false;
    laserDrawingRef.current = false;
    lastLaserPointRef.current = null;
    lastPointRef.current = null;
  };

  const handleCanvasWheel = (event: WheelEvent<HTMLCanvasElement>) => {
    if (tool === 'cursor' || event.ctrlKey) return;

    event.preventDefault();
    event.stopPropagation();

    if (activeFormat === 'html') {
      const frame = htmlFrameRef.current;
      const frameWindow = frame?.contentWindow;
      if (frame && frameWindow) {
        const rect = frame.getBoundingClientRect();
        frameWindow.postMessage(
          {
            clientX: event.clientX - rect.left,
            clientY: event.clientY - rect.top,
            deltaX: event.deltaX,
            deltaY: event.deltaY,
            type: 'open-work-hub-docs-html-wheel',
          },
          '*',
        );
      }
      return;
    }

    readViewportRef.current?.scrollBy({
      behavior: 'auto',
      left: event.deltaX,
      top: event.deltaY,
    });
  };

  return (
    <dialog
      open
      className="fixed inset-0 z-[140] m-0 flex h-screen w-screen max-w-none bg-[var(--ui-color-docs-read-bg)] p-0 text-white backdrop:bg-transparent"
      aria-label={t('apps:docs.readMode.title')}
    >
      <aside className="flex w-72 shrink-0 flex-col border-r border-white/10 bg-[var(--ui-color-docs-read-chrome)]">
        <div className="border-b border-white/10 p-4">
          <div className="flex items-center gap-2 text-white/60">
            <Maximize2 size={16} />
            <span className="app-text-overline">
              {t('apps:docs.readMode.title')}
            </span>
          </div>
          <h2 className="app-text-title-sm mt-2 line-clamp-2 text-white">
            {doc.title}
          </h2>
          <div className="app-text-caption mt-2 flex items-center gap-2 text-white/55">
            {activeFormat === 'html' ? (
              <FileCode2 size={13} />
            ) : (
              <FileText size={13} />
            )}
            <span>{activeLabel}</span>
            <span>
              {formatDocsReadPagePosition(activeIndex, flatPages.length)}
            </span>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <div className="app-text-overline mb-2 px-2 text-white/45">
            {t('apps:docs.pages')}
          </div>
          <div className="space-y-1">
            {flatPages.map(({ page, depth, format: pageFormat }, index) => {
              const isSelected = page.id === activePage.id;
              return (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => selectPageByIndex(index)}
                  className={cn(
                    'flex min-h-10 w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors',
                    isSelected
                      ? 'bg-white text-[var(--ui-color-docs-read-selected-fg)]'
                      : 'text-white/72 hover:bg-white/10 hover:text-white',
                  )}
                  style={{ paddingLeft: `${8 + depth * 14}px` }}
                >
                  {pageFormat === 'html' ? (
                    <FileCode2 size={14} />
                  ) : (
                    <FileText size={14} />
                  )}
                  <span className="app-text-body-sm min-w-0 flex-1 truncate">
                    {page.title}
                  </span>
                  <span className="app-text-micro tabular-nums opacity-60">
                    {index + 1}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-[var(--ui-color-docs-read-chrome)] px-4">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              disabled={activeIndex <= 0}
              onClick={() => selectPageByIndex(activeIndex - 1)}
              className="inline-flex size-9 items-center justify-center rounded-md text-white/75 hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
              aria-label={t('apps:docs.readMode.previousPage')}
            >
              <ChevronLeft size={18} />
            </button>
            <button
              type="button"
              disabled={activeIndex >= flatPages.length - 1}
              onClick={() => selectPageByIndex(activeIndex + 1)}
              className="inline-flex size-9 items-center justify-center rounded-md text-white/75 hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
              aria-label={t('apps:docs.readMode.nextPage')}
            >
              <ChevronRight size={18} />
            </button>
            <div className="min-w-0 pl-2">
              <h1 className="app-text-control truncate text-white">
                {activePage.title}
              </h1>
              <p className="app-text-caption text-white/50">
                {formatDocsReadPagePosition(activeIndex, flatPages.length)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeFormat === 'html' ? (
              <div
                className="flex h-9 items-center rounded-md border border-white/10 bg-white/5 p-1"
                aria-label={t('apps:docs.readMode.zoomControls')}
              >
                <button
                  type="button"
                  onClick={() => adjustHtmlZoom(-DOCS_HTML_ZOOM_STEP)}
                  disabled={htmlZoom <= DOCS_HTML_ZOOM_MIN}
                  className="inline-flex size-7 items-center justify-center rounded text-white/70 hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
                  aria-label={t('apps:docs.readMode.zoomOut')}
                  title={t('apps:docs.readMode.zoomOut')}
                >
                  <ZoomOut size={15} />
                </button>
                <span
                  data-testid="docs-html-zoom-label"
                  className="app-text-control-sm w-12 text-center tabular-nums text-white/80"
                >
                  {htmlZoomPercent}
                </span>
                <button
                  type="button"
                  onClick={() => adjustHtmlZoom(DOCS_HTML_ZOOM_STEP)}
                  disabled={htmlZoom >= DOCS_HTML_ZOOM_MAX}
                  className="inline-flex size-7 items-center justify-center rounded text-white/70 hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
                  aria-label={t('apps:docs.readMode.zoomIn')}
                  title={t('apps:docs.readMode.zoomIn')}
                >
                  <ZoomIn size={15} />
                </button>
                <button
                  type="button"
                  onClick={() => setHtmlZoom(1)}
                  disabled={htmlZoom === 1}
                  className="ml-1 inline-flex size-7 items-center justify-center rounded border-l border-white/10 text-white/70 hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-30"
                  aria-label={t('apps:docs.readMode.resetZoom')}
                  title={t('apps:docs.readMode.resetZoom')}
                >
                  <RotateCcw size={14} />
                </button>
              </div>
            ) : null}
            <div className="flex items-center rounded-md border border-white/10 bg-white/5 p-1">
              {(
                [
                  ['cursor', MousePointer2, t('apps:docs.readMode.cursor')],
                  ['laser', CircleDot, t('apps:docs.readMode.laser')],
                  ['pen', PenLine, t('apps:docs.readMode.pen')],
                ] as const
              ).map(([value, Icon, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setTool(value);
                    setLaserPoint(null);
                  }}
                  className={cn(
                    'app-text-control-sm inline-flex h-8 items-center gap-1.5 rounded px-2.5 transition-colors',
                    tool === value
                      ? 'bg-white text-[var(--ui-color-docs-read-selected-fg)]'
                      : 'text-white/70 hover:bg-white/10 hover:text-white',
                  )}
                  aria-pressed={tool === value}
                >
                  <Icon size={15} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={clearPresentationMarks}
              className="app-text-control-sm inline-flex h-9 items-center gap-1.5 rounded-md border border-white/10 px-3 text-white/75 hover:bg-white/10 hover:text-white"
            >
              <Eraser size={15} />
              <span>{t('apps:docs.readMode.clearInk')}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex size-9 items-center justify-center rounded-md text-white/75 hover:bg-white/10 hover:text-white"
              aria-label={t('apps:docs.readMode.close')}
            >
              <X size={19} />
            </button>
          </div>
        </header>

        <div className="relative min-h-0 flex-1 bg-[var(--ui-color-docs-read-bg)]">
          <div
            ref={readViewportRef}
            data-testid="docs-read-mode-viewport"
            className={cn(
              'h-full min-h-0 px-4 py-6 lg:px-8 lg:py-8',
              activeFormat === 'html' ? 'overflow-hidden' : 'overflow-auto',
            )}
          >
            <article
              data-testid="docs-read-mode-page"
              className={cn(
                'w-full rounded-md bg-white px-8 py-10 text-app-ink shadow-2xl dark:bg-app-surface lg:px-12',
                activeFormat === 'html'
                  ? 'flex h-full min-h-0 flex-col overflow-hidden'
                  : 'min-h-full',
              )}
            >
              <div className="mb-8 shrink-0 border-b border-app-border pb-5">
                <h2 className="app-text-title-xl text-app-ink">
                  {activePage.title}
                </h2>
                <p className="app-text-caption mt-2 text-app-ink/55">
                  {doc.title} · {activeLabel}
                </p>
              </div>
              {activeFormat === 'html' ? (
                activePage.content_text?.trim() ? (
                  <div
                    data-testid="docs-html-zoom-viewport"
                    className="min-h-0 flex-1 overflow-hidden rounded-md border border-app-border bg-white"
                  >
                    <div
                      data-testid="docs-html-zoom-layout"
                      className="h-full w-full"
                    >
                      <div
                        data-testid="docs-html-zoom-surface"
                        data-zoom={htmlZoom.toFixed(2)}
                        className="h-full w-full"
                      >
                        <DocsHtmlFrame
                          iframeRef={htmlFrameRef}
                          title={activePage.title}
                          content={activePage.content_text}
                          enableWheelBridge
                          zoom={htmlZoom}
                        />
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="app-text-body rounded-md border border-dashed border-app-border px-4 py-10 text-center text-app-ink/55">
                    {t('apps:docs.html.empty')}
                  </div>
                )
              ) : (
                <BlockViewer
                  key={activePage.id}
                  content={(activePage.content_blocks as BlockContent) ?? []}
                  resolveFileUrl={resolveFileUrl}
                  className="text-app-ink"
                />
              )}
            </article>
          </div>

          <canvas
            key={activePage.id}
            ref={canvasRef}
            className={cn(
              'absolute inset-0 h-full w-full',
              tool === 'cursor' ? 'pointer-events-none' : 'pointer-events-auto',
              tool === 'pen' && 'cursor-crosshair',
            )}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onWheel={handleCanvasWheel}
            onPointerUp={stopDrawing}
            onPointerCancel={stopDrawing}
            onPointerLeave={(event) => {
              if (tool === 'laser') setLaserPoint(null);
              stopDrawing(event);
            }}
          />
          <style>
            {`
              @keyframes docs-laser-mark-fade {
                0% {
                  opacity: 0.95;
                }
                65% {
                  opacity: 0.72;
                }
                100% {
                  opacity: 0;
                }
              }
            `}
          </style>
          <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
            {visibleLaserSegments.map((segment) => (
              <line
                key={segment.id}
                data-testid="docs-laser-segment"
                x1={segment.from.x}
                y1={segment.from.y}
                x2={segment.to.x}
                y2={segment.to.y}
                stroke="var(--ui-color-docs-laser)"
                strokeLinecap="round"
                strokeWidth={5}
                style={{
                  animation: 'docs-laser-mark-fade 900ms ease-out forwards',
                  filter: 'var(--ui-filter-docs-laser)',
                }}
              />
            ))}
          </svg>
          {tool === 'laser' && visibleLaserPoint ? (
            <div
              data-testid="docs-laser-pointer"
              className="pointer-events-none absolute size-2 rounded-full bg-[var(--ui-color-docs-laser)] [left:var(--docs-laser-x)] [top:var(--docs-laser-y)] [transform:translate(-50%,-50%)]"
              style={
                {
                  '--docs-laser-x': `${visibleLaserPoint.x}px`,
                  '--docs-laser-y': `${visibleLaserPoint.y}px`,
                } as CSSProperties
              }
            />
          ) : null}
        </div>
      </main>
    </dialog>
  );
}

function readDocsCssVariable(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  return (
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() ||
    fallback
  );
}
