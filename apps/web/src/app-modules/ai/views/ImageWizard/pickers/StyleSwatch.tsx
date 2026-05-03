import { useTranslation } from 'react-i18next';

import type { StylePreset, StyleShape } from '../style-presets';

interface StyleSwatchProps {
  preset: StylePreset;
  selected: boolean;
  onToggle: () => void;
}

export function StyleSwatch({ preset, selected, onToggle }: StyleSwatchProps) {
  const { t } = useTranslation('apps');
  const label = t(`ai.imageWizard.style.chips.${preset.id}`, { defaultValue: preset.id });

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={selected}
      className={`group flex w-[5.5rem] flex-col items-center gap-1.5 rounded-md border p-1.5 transition-all ${
        selected
          ? 'border-app-accent bg-app-accent/10 ring-2 ring-app-accent/40'
          : 'border-app-border bg-app-surface-sidebar hover:border-app-accent/50'
      }`}
    >
      <span className="block h-11 w-11 overflow-hidden rounded">
        <ShapeArt shape={preset.id} palette={preset.palette} />
      </span>
      <span className="flex gap-0.5">
        {preset.palette.map((color, idx) => (
          <span
            key={`${color}-${idx}`}
            className="block h-1.5 w-1.5 rounded-full"
            style={{ background: color }}
            aria-hidden
          />
        ))}
      </span>
      <span className="line-clamp-1 text-center text-[10px] leading-tight text-app-ink/70 group-hover:text-app-ink">
        {label}
      </span>
    </button>
  );
}

interface ShapeArtProps {
  shape: StyleShape;
  palette: [string, string, string, string];
}

function ShapeArt({ shape, palette }: ShapeArtProps) {
  const [a, b, c, d] = palette;

  switch (shape) {
    case 'corporate':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <rect x="6" y="8" width="32" height="3" fill={a} />
          <rect x="6" y="14" width="20" height="2" fill={d} />
          <rect x="6" y="22" width="14" height="14" fill={b} opacity="0.85" />
          <rect x="24" y="22" width="14" height="14" fill={a} opacity="0.6" />
        </svg>
      );
    case 'magazine':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <text x="6" y="20" fill={a} fontFamily="serif" fontWeight="700" fontSize="18">
            Aa
          </text>
          <rect x="6" y="26" width="32" height="2" fill={a} />
          <rect x="6" y="30" width="24" height="1.4" fill={d} />
          <rect x="6" y="34" width="28" height="1.4" fill={d} />
          <rect x="34" y="6" width="6" height="6" fill={b} />
        </svg>
      );
    case 'newspaper':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <text x="6" y="13" fill={a} fontFamily="serif" fontWeight="900" fontSize="9">
            {'HEAD'}
          </text>
          <rect x="6" y="17" width="32" height="0.6" fill={a} />
          {Array.from({ length: 7 }).map((_, idx) => (
            <rect key={idx} x="6" y={20 + idx * 3} width="32" height="0.6" fill={b} opacity="0.6" />
          ))}
        </svg>
      );
    case 'bauhaus':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={d === '#0A0A0A' ? '#fafafa' : '#fafafa'} />
          <circle cx="14" cy="22" r="11" fill={a} />
          <rect x="22" y="6" width="16" height="16" fill={b} />
          <polygon points="22,38 38,22 38,38" fill={c} />
        </svg>
      );
    case 'swiss':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <rect x="6" y="6" width="20" height="3" fill={a} />
          <rect x="6" y="12" width="14" height="1.4" fill={a} />
          <rect x="6" y="20" width="32" height="18" fill={b} />
        </svg>
      );
    case 'blueprint':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={a} />
          {Array.from({ length: 6 }).map((_, idx) => (
            <line key={`h${idx}`} x1="0" y1={idx * 8 + 2} x2="44" y2={idx * 8 + 2} stroke={b} strokeWidth="0.4" opacity="0.4" />
          ))}
          {Array.from({ length: 6 }).map((_, idx) => (
            <line key={`v${idx}`} x1={idx * 8 + 2} y1="0" x2={idx * 8 + 2} y2="44" stroke={b} strokeWidth="0.4" opacity="0.4" />
          ))}
          <rect x="10" y="14" width="20" height="14" stroke={c} strokeWidth="1.2" fill="none" />
          <line x1="14" y1="18" x2="26" y2="18" stroke={c} strokeWidth="0.8" />
        </svg>
      );
    case 'dataviz':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill="#0F172A" opacity="0.05" />
          <rect x="6" y="26" width="6" height="12" fill={a} />
          <rect x="14" y="18" width="6" height="20" fill={b} />
          <rect x="22" y="22" width="6" height="16" fill={c} />
          <rect x="30" y="14" width="6" height="24" fill={d} />
          <line x1="6" y1="40" x2="38" y2="40" stroke="#0F172A" strokeWidth="0.6" opacity="0.4" />
        </svg>
      );
    case 'wireframe':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <rect x="6" y="6" width="32" height="6" stroke={a} strokeWidth="0.8" fill="none" />
          <rect x="6" y="16" width="14" height="22" stroke={a} strokeWidth="0.8" fill="none" />
          <rect x="22" y="16" width="16" height="10" stroke={a} strokeWidth="0.8" fill="none" />
          <rect x="22" y="28" width="16" height="10" stroke={a} strokeWidth="0.8" fill="none" />
        </svg>
      );
    case 'isometric':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill="#fafafa" />
          <polygon points="22,8 36,16 22,24 8,16" fill={a} opacity="0.85" />
          <polygon points="22,24 36,16 36,32 22,40" fill={b} opacity="0.7" />
          <polygon points="22,24 8,16 8,32 22,40" fill={c} opacity="0.5" />
        </svg>
      );
    case 'flow':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <circle cx="10" cy="22" r="5" fill={a} />
          <circle cx="22" cy="22" r="5" fill={b} />
          <circle cx="34" cy="22" r="5" fill={d} />
          <line x1="15" y1="22" x2="17" y2="22" stroke={d} strokeWidth="1.2" />
          <line x1="27" y1="22" x2="29" y2="22" stroke={d} strokeWidth="1.2" />
        </svg>
      );
    case 'mindmap':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill="#fafafa" />
          <circle cx="22" cy="22" r="6" fill={a} />
          <circle cx="8" cy="10" r="3.5" fill={b} />
          <circle cx="36" cy="10" r="3.5" fill={c} />
          <circle cx="8" cy="34" r="3.5" fill={d} />
          <circle cx="36" cy="34" r="3.5" fill={b} />
          <line x1="11" y1="13" x2="18" y2="19" stroke={a} strokeWidth="0.6" />
          <line x1="33" y1="13" x2="26" y2="19" stroke={a} strokeWidth="0.6" />
          <line x1="11" y1="31" x2="18" y2="25" stroke={a} strokeWidth="0.6" />
          <line x1="33" y1="31" x2="26" y2="25" stroke={a} strokeWidth="0.6" />
        </svg>
      );
    case 'orgchart':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <rect x="17" y="6" width="10" height="6" fill={a} />
          <line x1="22" y1="12" x2="22" y2="18" stroke={a} strokeWidth="0.8" />
          <line x1="10" y1="18" x2="34" y2="18" stroke={a} strokeWidth="0.8" />
          <line x1="10" y1="18" x2="10" y2="22" stroke={a} strokeWidth="0.8" />
          <line x1="22" y1="18" x2="22" y2="22" stroke={a} strokeWidth="0.8" />
          <line x1="34" y1="18" x2="34" y2="22" stroke={a} strokeWidth="0.8" />
          <rect x="6" y="22" width="8" height="6" fill={b} />
          <rect x="18" y="22" width="8" height="6" fill={b} />
          <rect x="30" y="22" width="8" height="6" fill={b} />
        </svg>
      );
    case 'flat':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill="#FAF5FF" />
          <circle cx="14" cy="20" r="8" fill={a} />
          <rect x="22" y="14" width="14" height="14" rx="3" fill={b} />
          <path d="M6 38 L20 30 L38 38 Z" fill={c} />
        </svg>
      );
    case 'doodle':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={b} />
          <path d="M8 12 Q14 6, 22 12 T36 12" stroke={a} strokeWidth="1.2" fill="none" strokeLinecap="round" />
          <circle cx="14" cy="24" r="4" stroke={a} strokeWidth="1" fill="none" />
          <path d="M22 22 L34 22 L30 30 L22 30 Z" stroke={a} strokeWidth="1" fill="none" />
          <circle cx="34" cy="34" r="2" fill={c} />
        </svg>
      );
    case 'watercolor':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill="#FFFBF5" />
          <circle cx="14" cy="16" r="11" fill={a} opacity="0.7" />
          <circle cx="28" cy="22" r="9" fill={b} opacity="0.6" />
          <circle cx="20" cy="32" r="10" fill={c} opacity="0.55" />
          <circle cx="34" cy="34" r="6" fill={d} opacity="0.55" />
        </svg>
      );
    case 'risograph':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <circle cx="18" cy="20" r="10" fill={a} opacity="0.85" />
          <circle cx="26" cy="24" r="10" fill={b} opacity="0.7" style={{ mixBlendMode: 'multiply' }} />
          <text x="6" y="40" fontFamily="monospace" fontWeight="700" fontSize="6" fill={d}>RISO</text>
        </svg>
      );
    case 'cutpaper':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={d} />
          <polygon points="0,32 12,20 22,28 32,18 44,28 44,44 0,44" fill={c} />
          <polygon points="0,38 14,28 26,34 36,26 44,32 44,44 0,44" fill={b} />
          <polygon points="0,42 16,34 28,38 44,36 44,44 0,44" fill={a} />
        </svg>
      );
    case 'comic':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={b} />
          <path d="M6 6 L24 6 L28 14 L24 22 L6 22 Z" fill={c} stroke={d} strokeWidth="1.4" />
          <text x="10" y="17" fontWeight="900" fontSize="9" fill={d} fontFamily="sans-serif">POW!</text>
          <circle cx="34" cy="32" r="8" fill={a} stroke={d} strokeWidth="1.4" />
        </svg>
      );
    case 'photoreal':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <defs>
            <linearGradient id="ph-g" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor={c} />
              <stop offset="1" stopColor={a} />
            </linearGradient>
          </defs>
          <rect width="44" height="44" fill="url(#ph-g)" />
          <ellipse cx="32" cy="14" rx="6" ry="6" fill={d} opacity="0.4" />
          <rect x="0" y="30" width="44" height="14" fill={a} opacity="0.6" />
        </svg>
      );
    case 'mono':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={a} />
          <rect x="8" y="8" width="28" height="28" fill={d} />
          <rect x="14" y="14" width="16" height="2" fill={a} />
          <rect x="14" y="20" width="10" height="2" fill={a} />
        </svg>
      );
    case 'kawaii':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <circle cx="22" cy="24" r="12" fill={a} />
          <circle cx="17" cy="22" r="1.4" fill="#1F2937" />
          <circle cx="27" cy="22" r="1.4" fill="#1F2937" />
          <path d="M18 27 Q22 30, 26 27" stroke="#1F2937" strokeWidth="1" fill="none" strokeLinecap="round" />
          <circle cx="14" cy="26" r="1.5" fill={d} />
          <circle cx="30" cy="26" r="1.5" fill={d} />
        </svg>
      );
    case 'cyberpunk':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={d} />
          <rect x="6" y="10" width="32" height="2" fill={a} opacity="0.9" />
          <rect x="6" y="14" width="20" height="1" fill={b} opacity="0.6" />
          <rect x="6" y="22" width="32" height="3" fill={c} />
          <text x="6" y="36" fontFamily="monospace" fontWeight="700" fontSize="7" fill={a}>{'> NEON'}</text>
        </svg>
      );
    case 'y2k':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <defs>
            <radialGradient id="y2k-g" cx="50%" cy="50%" r="55%">
              <stop offset="0" stopColor={b} />
              <stop offset="0.6" stopColor={a} />
              <stop offset="1" stopColor={d} />
            </radialGradient>
          </defs>
          <rect width="44" height="44" fill="url(#y2k-g)" />
          <circle cx="22" cy="22" r="9" fill={c} opacity="0.8" />
          <circle cx="22" cy="22" r="3" fill={d} />
        </svg>
      );
    case 'koreanmodern':
      return (
        <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden>
          <rect width="44" height="44" fill={c} />
          <rect x="0" y="0" width="44" height="6" fill={a} />
          <text x="6" y="22" fontFamily="serif" fontWeight="700" fontSize="14" fill={a}>韓</text>
          <rect x="6" y="28" width="20" height="1.5" fill={b} />
          <rect x="6" y="32" width="28" height="1" fill={d} />
          <circle cx="34" cy="32" r="3" fill={d} />
        </svg>
      );
  }
}

export default StyleSwatch;
