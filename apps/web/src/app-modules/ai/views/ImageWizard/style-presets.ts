export const STYLE_GROUPS = [
  'editorial',
  'diagrammatic',
  'illustrative',
  'photo',
] as const;
export type StyleGroupId = (typeof STYLE_GROUPS)[number];

export type StyleShape =
  | 'corporate'
  | 'magazine'
  | 'newspaper'
  | 'bauhaus'
  | 'swiss'
  | 'blueprint'
  | 'infographic'
  | 'wireframe'
  | 'isometric'
  | 'flow'
  | 'mindmap'
  | 'flat'
  | 'doodle'
  | 'watercolor'
  | 'risograph'
  | 'cutpaper'
  | 'comic'
  | 'photoreal'
  | 'mono'
  | 'kawaii'
  | 'cyberpunk'
  | 'y2k'
  | 'koreanmodern';

export interface StylePreset {
  id: StyleShape;
  group: StyleGroupId;
  palette: [string, string, string, string];
}

type StylePalette = StylePreset['palette'];

const IMAGE_STYLE_PALETTES = {
  corporate: ['#1F3A8A', '#2563EB', '#E2E8F0', '#0F172A'],
  magazine: ['#111827', '#F59E0B', '#FFFBEB', '#1F2937'],
  newspaper: ['#1A1A1A', '#525252', '#F4F1EA', '#737373'],
  bauhaus: ['#DC2626', '#FACC15', '#1D4ED8', '#0A0A0A'],
  swiss: ['#000000', '#EF4444', '#FFFFFF', '#A3A3A3'],
  blueprint: ['#0E3F66', '#3B82F6', '#DBEAFE', '#FFFFFF'],
  infographic: ['#10B981', '#3B82F6', '#F59E0B', '#EF4444'],
  wireframe: ['#475569', '#94A3B8', '#F1F5F9', '#0F172A'],
  isometric: ['#7C3AED', '#22D3EE', '#FACC15', '#0F172A'],
  flow: ['#2563EB', '#0EA5E9', '#E2E8F0', '#1E293B'],
  mindmap: ['#9333EA', '#EC4899', '#22C55E', '#F59E0B'],
  flat: ['#3B82F6', '#F472B6', '#FACC15', '#1F2937'],
  doodle: ['#0F172A', '#FFFFFF', '#FACC15', '#EF4444'],
  watercolor: ['#FCA5A5', '#A5F3FC', '#FCD34D', '#C4B5FD'],
  risograph: ['#EC4899', '#06B6D4', '#FDE047', '#1F2937'],
  cutpaper: ['#FB923C', '#84CC16', '#0EA5E9', '#FAF5FF'],
  comic: ['#DC2626', '#FACC15', '#1D4ED8', '#000000'],
  photoreal: ['#1F2937', '#6B7280', '#D1D5DB', '#F9FAFB'],
  mono: ['#FFFFFF', '#A3A3A3', '#525252', '#0A0A0A'],
  kawaii: ['#FBCFE8', '#FBCFE8', '#A7F3D0', '#FEF3C7'],
  cyberpunk: ['#22D3EE', '#F472B6', '#A855F7', '#0F172A'],
  y2k: ['#A78BFA', '#22D3EE', '#FBBF24', '#1E1B4B'],
  koreanmodern: ['#1F2937', '#D6D3D1', '#FFFFFF', '#7C2D12'],
} satisfies Record<StyleShape, StylePalette>;

const STYLE_PRESETS: StylePreset[] = [
  // Editorial / Print
  {
    id: 'corporate',
    group: 'editorial',
    palette: IMAGE_STYLE_PALETTES.corporate,
  },
  {
    id: 'magazine',
    group: 'editorial',
    palette: IMAGE_STYLE_PALETTES.magazine,
  },
  {
    id: 'newspaper',
    group: 'editorial',
    palette: IMAGE_STYLE_PALETTES.newspaper,
  },
  { id: 'bauhaus', group: 'editorial', palette: IMAGE_STYLE_PALETTES.bauhaus },
  { id: 'swiss', group: 'editorial', palette: IMAGE_STYLE_PALETTES.swiss },
  {
    id: 'blueprint',
    group: 'editorial',
    palette: IMAGE_STYLE_PALETTES.blueprint,
  },

  // Diagrammatic
  {
    id: 'infographic',
    group: 'diagrammatic',
    palette: IMAGE_STYLE_PALETTES.infographic,
  },
  {
    id: 'wireframe',
    group: 'diagrammatic',
    palette: IMAGE_STYLE_PALETTES.wireframe,
  },
  {
    id: 'isometric',
    group: 'diagrammatic',
    palette: IMAGE_STYLE_PALETTES.isometric,
  },
  { id: 'flow', group: 'diagrammatic', palette: IMAGE_STYLE_PALETTES.flow },
  {
    id: 'mindmap',
    group: 'diagrammatic',
    palette: IMAGE_STYLE_PALETTES.mindmap,
  },

  // Illustrative
  { id: 'flat', group: 'illustrative', palette: IMAGE_STYLE_PALETTES.flat },
  { id: 'doodle', group: 'illustrative', palette: IMAGE_STYLE_PALETTES.doodle },
  {
    id: 'watercolor',
    group: 'illustrative',
    palette: IMAGE_STYLE_PALETTES.watercolor,
  },
  {
    id: 'risograph',
    group: 'illustrative',
    palette: IMAGE_STYLE_PALETTES.risograph,
  },
  {
    id: 'cutpaper',
    group: 'illustrative',
    palette: IMAGE_STYLE_PALETTES.cutpaper,
  },
  { id: 'comic', group: 'illustrative', palette: IMAGE_STYLE_PALETTES.comic },

  // Photo & Vibe
  { id: 'photoreal', group: 'photo', palette: IMAGE_STYLE_PALETTES.photoreal },
  { id: 'mono', group: 'photo', palette: IMAGE_STYLE_PALETTES.mono },
  { id: 'kawaii', group: 'photo', palette: IMAGE_STYLE_PALETTES.kawaii },
  { id: 'cyberpunk', group: 'photo', palette: IMAGE_STYLE_PALETTES.cyberpunk },
  { id: 'y2k', group: 'photo', palette: IMAGE_STYLE_PALETTES.y2k },
  {
    id: 'koreanmodern',
    group: 'photo',
    palette: IMAGE_STYLE_PALETTES.koreanmodern,
  },
];

export const STYLES_BY_GROUP: Record<StyleGroupId, StylePreset[]> =
  STYLE_GROUPS.reduce(
    (acc, group) => {
      acc[group] = STYLE_PRESETS.filter((preset) => preset.group === group);
      return acc;
    },
    {} as Record<StyleGroupId, StylePreset[]>,
  );

export const STYLE_IDS = STYLE_PRESETS.map((preset) => preset.id);
