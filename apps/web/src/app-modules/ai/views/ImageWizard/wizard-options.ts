export const USE_CASE_OPTIONS = [
  'meeting_deck',
  'report_cover',
  'docs_hero',
  'status_report',
  'process_flow',
  'comparison',
  'timeline',
  'quote_card',
  'social_header',
  'other',
] as const;
export type UseCaseId = (typeof USE_CASE_OPTIONS)[number];

export const STYLE_CHIPS = [
  'clean_corporate',
  'editorial',
  'hand_drawn',
  'data_viz',
  'flat_illustration',
  'photo_real',
  'minimal_mono',
] as const;
export type StyleChipId = (typeof STYLE_CHIPS)[number];

export const PALETTE_OPTIONS = [
  'auto',
  'brand',
  'warm',
  'cool',
  'monochrome',
  'vivid',
] as const;
export type PaletteId = (typeof PALETTE_OPTIONS)[number];

export const BACKGROUND_OPTIONS = ['auto', 'transparent', 'white', 'dark'] as const;
export type BackgroundId = (typeof BACKGROUND_OPTIONS)[number];

export const QUALITY_OPTIONS = ['low', 'medium', 'high', 'auto'] as const;
export type QualityId = (typeof QUALITY_OPTIONS)[number];

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

export const REFERENCE_ROLE_OPTIONS = ['style', 'composition', 'content'] as const;
export type ReferenceRoleId = (typeof REFERENCE_ROLE_OPTIONS)[number];

export const MAX_REFERENCE_IMAGES = 4;
