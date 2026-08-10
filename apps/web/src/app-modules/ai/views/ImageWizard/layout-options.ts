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
