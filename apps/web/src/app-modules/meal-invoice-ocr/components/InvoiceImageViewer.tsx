import { Maximize2, Minus, Plus, RotateCw, Scan } from 'lucide-react';
import {
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';

// 원본 명세표 뷰어: 확대/축소(＋/－·맞춤) + 확대 상태에서 드래그로 이동(pan).
// 스탠드얼론 HTML 프로그램의 사진 뷰어 동작을 그대로 옮겨온다(스크롤 기반 pan).
const MIN_ZOOM = 1;
const MAX_ZOOM = 6;
const ZOOM_STEP = 0.25;

interface InvoiceImageViewerProps {
  src: string;
  alt: string;
  // 좌우 2단에서 이미지 열이 차지할 폭(%). 분할선 드래그로 바뀐다(lg 이상에서만 적용).
  widthPct: number;
  onRotate: () => void;
  onEnlarge: () => void;
}

export function InvoiceImageViewer({
  src,
  alt,
  widthPct,
  onRotate,
  onEnlarge,
}: InvoiceImageViewerProps) {
  const { t } = useTranslation(['apps']);
  const [zoom, setZoom] = useState(1);
  const [grabbing, setGrabbing] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // 드래그 시작 시점의 마우스 좌표와 스크롤 위치(이 기준으로 pan 오프셋 계산).
  const panRef = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  // 휠 줌 후 커서 지점을 유지하기 위해 다음 렌더에서 적용할 스크롤 위치.
  const pendingScrollRef = useRef<{ left: number; top: number } | null>(null);

  const clamp = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
  const zoomIn = useCallback(() => setZoom((z) => clamp(z + ZOOM_STEP)), []);
  const zoomOut = useCallback(() => setZoom((z) => clamp(z - ZOOM_STEP)), []);
  const fit = useCallback(() => {
    setZoom(1);
    const el = scrollRef.current;
    if (el) {
      el.scrollLeft = 0;
      el.scrollTop = 0;
    }
  }, []);

  const onMouseDown = useCallback(
    (e: ReactMouseEvent) => {
      const el = scrollRef.current;
      if (!el || zoom <= 1) return;
      panRef.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop };
      setGrabbing(true);
      e.preventDefault();
    },
    [zoom],
  );

  // pan/해제는 window 에 걸어 이미지 밖으로 벗어나도 계속 잡히게 한다.
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const pan = panRef.current;
      const el = scrollRef.current;
      if (!pan || !el) return;
      el.scrollLeft = pan.left - (e.clientX - pan.x);
      el.scrollTop = pan.top - (e.clientY - pan.y);
    };
    const onUp = () => {
      if (panRef.current) {
        panRef.current = null;
        setGrabbing(false);
      }
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);

  // 휠 줌: 커서 아래 지점이 그대로 유지되도록 확대·축소. 페이지 스크롤은 막는다(passive:false 필요).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      setZoom((old) => {
        const next = clamp(e.deltaY < 0 ? old * 1.15 : old / 1.15);
        if (next === old) return old;
        const ratio = next / old;
        pendingScrollRef.current = {
          left: (el.scrollLeft + cx) * ratio - cx,
          top: (el.scrollTop + cy) * ratio - cy,
        };
        return next;
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // 줌이 반영돼 이미지 폭이 바뀐 직후, 휠 줌에서 계산한 커서 기준 스크롤을 적용.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && pendingScrollRef.current) {
      el.scrollLeft = pendingScrollRef.current.left;
      el.scrollTop = pendingScrollRef.current.top;
      pendingScrollRef.current = null;
    }
  }, [zoom]);

  const zoomable = zoom > 1;
  const cursor = zoomable ? (grabbing ? 'grabbing' : 'grab') : 'default';

  return (
    <div
      className="flex flex-col rounded-md border border-gray-100 bg-gray-50 lg:order-1 lg:w-[var(--imgw,46%)] lg:shrink-0 lg:self-start lg:sticky lg:top-4"
      style={{ '--imgw': `${widthPct}%` } as CSSProperties}
    >
      <div className="flex flex-wrap items-center gap-1 border-b border-gray-100 px-2 py-1">
        <button
          type="button"
          onClick={zoomOut}
          disabled={zoom <= MIN_ZOOM}
          title={t('apps:mealInvoiceOcr.actions.zoomOut')}
          className="inline-flex h-6 w-6 items-center justify-center rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 disabled:opacity-40"
        >
          <Minus className="h-3.5 w-3.5" />
        </button>
        <span className="min-w-[3rem] text-center text-xs tabular-nums text-gray-500">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={zoomIn}
          disabled={zoom >= MAX_ZOOM}
          title={t('apps:mealInvoiceOcr.actions.zoomIn')}
          className="inline-flex h-6 w-6 items-center justify-center rounded border border-gray-300 bg-white text-gray-600 hover:bg-gray-100 disabled:opacity-40"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={fit}
          title={t('apps:mealInvoiceOcr.actions.fit')}
          className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
        >
          <Scan className="h-3.5 w-3.5" />
          {t('apps:mealInvoiceOcr.actions.fit')}
        </button>
        <div className="ml-auto flex gap-1">
          <button
            type="button"
            onClick={onRotate}
            title={t('apps:mealInvoiceOcr.actions.rotate')}
            className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
          >
            <RotateCw className="h-3.5 w-3.5" />
            {t('apps:mealInvoiceOcr.actions.rotate')}
          </button>
          <button
            type="button"
            onClick={onEnlarge}
            title={t('apps:mealInvoiceOcr.actions.enlarge')}
            className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-100"
          >
            <Maximize2 className="h-3.5 w-3.5" />
            {t('apps:mealInvoiceOcr.actions.enlarge')}
          </button>
        </div>
      </div>
      <div
        ref={scrollRef}
        onMouseDown={onMouseDown}
        className="max-h-[78vh] overflow-auto"
        style={{ cursor }}
        title={t('apps:mealInvoiceOcr.actions.zoomHint')}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          className="mx-auto block select-none object-contain"
          style={{ width: `${zoom * 100}%`, maxWidth: 'none' }}
        />
      </div>
    </div>
  );
}
