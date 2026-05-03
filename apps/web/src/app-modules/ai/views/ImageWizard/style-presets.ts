export const STYLE_GROUPS = ['editorial', 'diagrammatic', 'illustrative', 'photo'] as const;
export type StyleGroupId = (typeof STYLE_GROUPS)[number];

export type StyleShape =
  | 'corporate'
  | 'magazine'
  | 'newspaper'
  | 'bauhaus'
  | 'swiss'
  | 'blueprint'
  | 'dataviz'
  | 'wireframe'
  | 'isometric'
  | 'flow'
  | 'mindmap'
  | 'orgchart'
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

export const STYLE_PRESETS: StylePreset[] = [
  // Editorial / Print
  { id: 'corporate', group: 'editorial', palette: ['#1F3A8A', '#2563EB', '#E2E8F0', '#0F172A'] },
  { id: 'magazine', group: 'editorial', palette: ['#111827', '#F59E0B', '#FFFBEB', '#1F2937'] },
  { id: 'newspaper', group: 'editorial', palette: ['#1A1A1A', '#525252', '#F4F1EA', '#737373'] },
  { id: 'bauhaus', group: 'editorial', palette: ['#DC2626', '#FACC15', '#1D4ED8', '#0A0A0A'] },
  { id: 'swiss', group: 'editorial', palette: ['#000000', '#EF4444', '#FFFFFF', '#A3A3A3'] },
  { id: 'blueprint', group: 'editorial', palette: ['#0E3F66', '#3B82F6', '#DBEAFE', '#FFFFFF'] },

  // Diagrammatic
  { id: 'dataviz', group: 'diagrammatic', palette: ['#10B981', '#3B82F6', '#F59E0B', '#EF4444'] },
  { id: 'wireframe', group: 'diagrammatic', palette: ['#475569', '#94A3B8', '#F1F5F9', '#0F172A'] },
  { id: 'isometric', group: 'diagrammatic', palette: ['#7C3AED', '#22D3EE', '#FACC15', '#0F172A'] },
  { id: 'flow', group: 'diagrammatic', palette: ['#2563EB', '#0EA5E9', '#E2E8F0', '#1E293B'] },
  { id: 'mindmap', group: 'diagrammatic', palette: ['#9333EA', '#EC4899', '#22C55E', '#F59E0B'] },
  { id: 'orgchart', group: 'diagrammatic', palette: ['#1E40AF', '#64748B', '#F8FAFC', '#0F172A'] },

  // Illustrative
  { id: 'flat', group: 'illustrative', palette: ['#3B82F6', '#F472B6', '#FACC15', '#1F2937'] },
  { id: 'doodle', group: 'illustrative', palette: ['#0F172A', '#FFFFFF', '#FACC15', '#EF4444'] },
  { id: 'watercolor', group: 'illustrative', palette: ['#FCA5A5', '#A5F3FC', '#FCD34D', '#C4B5FD'] },
  { id: 'risograph', group: 'illustrative', palette: ['#EC4899', '#06B6D4', '#FDE047', '#1F2937'] },
  { id: 'cutpaper', group: 'illustrative', palette: ['#FB923C', '#84CC16', '#0EA5E9', '#FAF5FF'] },
  { id: 'comic', group: 'illustrative', palette: ['#DC2626', '#FACC15', '#1D4ED8', '#000000'] },

  // Photo & Vibe
  { id: 'photoreal', group: 'photo', palette: ['#1F2937', '#6B7280', '#D1D5DB', '#F9FAFB'] },
  { id: 'mono', group: 'photo', palette: ['#FFFFFF', '#A3A3A3', '#525252', '#0A0A0A'] },
  { id: 'kawaii', group: 'photo', palette: ['#FBCFE8', '#FBCFE8', '#A7F3D0', '#FEF3C7'] },
  { id: 'cyberpunk', group: 'photo', palette: ['#22D3EE', '#F472B6', '#A855F7', '#0F172A'] },
  { id: 'y2k', group: 'photo', palette: ['#A78BFA', '#22D3EE', '#FBBF24', '#1E1B4B'] },
  { id: 'koreanmodern', group: 'photo', palette: ['#1F2937', '#D6D3D1', '#FFFFFF', '#7C2D12'] },
];

export const STYLES_BY_GROUP: Record<StyleGroupId, StylePreset[]> = STYLE_GROUPS.reduce(
  (acc, group) => {
    acc[group] = STYLE_PRESETS.filter((preset) => preset.group === group);
    return acc;
  },
  {} as Record<StyleGroupId, StylePreset[]>,
);

export const STYLE_IDS = STYLE_PRESETS.map((preset) => preset.id);
