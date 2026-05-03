export const LAYOUT_OPTIONS = [
  'single_focus',
  'left_text_right_visual',
  'top_title_grid',
  'three_column',
  'two_row_comparison',
  'timeline_horizontal',
  'freeform',
] as const;
export type LayoutId = (typeof LAYOUT_OPTIONS)[number];

export const ASPECT_OPTIONS = ['1024x1024', '1536x1024', '1024x1536'] as const;
export type AspectId = (typeof ASPECT_OPTIONS)[number];

interface WireframeProps {
  className?: string;
}

const FRAME = 'rgba(15,23,42,0.16)';
const FILL_BLOCK = 'rgba(15,23,42,0.06)';
const FILL_HEAVY = 'rgba(15,23,42,0.18)';
const ACCENT = 'currentColor';

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox="0 0 80 50" width="80" height="50" aria-hidden>
      <rect x="0.5" y="0.5" width="79" height="49" fill="none" stroke={FRAME} strokeWidth="1" rx="3" />
      {children}
    </svg>
  );
}

export function LayoutWireframe({ id, className }: WireframeProps & { id: LayoutId }) {
  return (
    <span className={className} style={{ display: 'inline-flex' }}>
      {(() => {
        switch (id) {
          case 'single_focus':
            return (
              <Frame>
                <rect x="20" y="12" width="40" height="26" fill={ACCENT} opacity="0.65" rx="2" />
              </Frame>
            );
          case 'left_text_right_visual':
            return (
              <Frame>
                <rect x="6" y="10" width="28" height="3" fill={ACCENT} opacity="0.9" />
                <rect x="6" y="16" width="22" height="2" fill={FILL_HEAVY} />
                <rect x="6" y="20" width="24" height="2" fill={FILL_HEAVY} />
                <rect x="6" y="24" width="20" height="2" fill={FILL_HEAVY} />
                <rect x="40" y="10" width="34" height="30" fill={ACCENT} opacity="0.55" rx="2" />
              </Frame>
            );
          case 'top_title_grid':
            return (
              <Frame>
                <rect x="6" y="6" width="50" height="3" fill={ACCENT} opacity="0.9" />
                <rect x="6" y="11" width="34" height="2" fill={FILL_HEAVY} />
                <rect x="6" y="18" width="34" height="11" fill={FILL_BLOCK} rx="1.5" />
                <rect x="42" y="18" width="32" height="11" fill={FILL_BLOCK} rx="1.5" />
                <rect x="6" y="32" width="34" height="11" fill={FILL_BLOCK} rx="1.5" />
                <rect x="42" y="32" width="32" height="11" fill={FILL_BLOCK} rx="1.5" />
              </Frame>
            );
          case 'three_column':
            return (
              <Frame>
                <rect x="6" y="10" width="20" height="30" fill={FILL_BLOCK} rx="1.5" />
                <rect x="30" y="10" width="20" height="30" fill={FILL_BLOCK} rx="1.5" />
                <rect x="54" y="10" width="20" height="30" fill={FILL_BLOCK} rx="1.5" />
                <rect x="9" y="14" width="14" height="2" fill={ACCENT} opacity="0.7" />
                <rect x="33" y="14" width="14" height="2" fill={ACCENT} opacity="0.7" />
                <rect x="57" y="14" width="14" height="2" fill={ACCENT} opacity="0.7" />
              </Frame>
            );
          case 'two_row_comparison':
            return (
              <Frame>
                <rect x="6" y="6" width="68" height="18" fill={FILL_BLOCK} rx="2" />
                <rect x="6" y="26" width="68" height="18" fill={ACCENT} opacity="0.55" rx="2" />
                <rect x="34" y="6" width="12" height="38" fill="white" opacity="0.7" />
              </Frame>
            );
          case 'timeline_horizontal':
            return (
              <Frame>
                <line x1="8" y1="25" x2="72" y2="25" stroke={FILL_HEAVY} strokeWidth="1.5" />
                {[12, 24, 36, 48, 60, 72].map((cx) => (
                  <circle key={cx} cx={cx} cy="25" r="2.4" fill={ACCENT} opacity="0.85" />
                ))}
                {[12, 24, 36, 48, 60, 72].map((cx, idx) => (
                  <rect key={`l-${cx}`} x={cx - 3} y={idx % 2 === 0 ? 32 : 14} width="10" height="2" fill={FILL_HEAVY} />
                ))}
              </Frame>
            );
          case 'freeform':
            return (
              <Frame>
                <circle cx="20" cy="18" r="9" fill={ACCENT} opacity="0.55" />
                <rect x="32" y="20" width="22" height="14" fill={FILL_BLOCK} rx="2" />
                <polygon points="55,15 70,15 62,32" fill={ACCENT} opacity="0.4" />
                <line x1="6" y1="42" x2="74" y2="42" stroke={FILL_HEAVY} strokeWidth="0.8" />
              </Frame>
            );
        }
      })()}
    </span>
  );
}

const ASPECT_BOX: Record<AspectId, { w: number; h: number }> = {
  '1024x1024': { w: 32, h: 32 },
  '1536x1024': { w: 44, h: 28 },
  '1024x1536': { w: 28, h: 44 },
};

export function AspectThumb({ id }: { id: AspectId }) {
  const box = ASPECT_BOX[id];
  return (
    <span
      className="block rounded border border-current opacity-70"
      style={{ width: box.w, height: box.h }}
      aria-hidden
    />
  );
}
