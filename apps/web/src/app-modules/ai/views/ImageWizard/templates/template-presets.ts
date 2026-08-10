import type { LayoutId, AspectId } from '../layout-wireframes';
import type { StyleShape } from '../style-presets';
import type { TemplateMockupId } from './mockups';

export const TEMPLATE_CATEGORIES = ['deck', 'report', 'diagram', 'card', 'social'] as const;
export type TemplateCategoryId = (typeof TEMPLATE_CATEGORIES)[number];
const USER_TEMPLATE_PREFIX = 'user_template:';

export interface TemplatePreset {
  id: string;
  category: TemplateCategoryId;
  mockupId: TemplateMockupId;
  name?: string;
  hint?: string;
  previewUrl?: string;
  sourceGenerationId?: string;
  preset: {
    use_case: string;
    style: {
      chips: StyleShape[];
      palette: string;
      background: string;
      quality: string;
    };
    layout: { layout_id: LayoutId; aspect: AspectId };
  };
}

export function getBuiltinTemplatePreviewUrl(templateId: string): string {
  return `/image-wizard/templates/${templateId}.png`;
}

export function makeUserTemplateId(generationId: string): string {
  return `${USER_TEMPLATE_PREFIX}${generationId}`;
}

export function getUserTemplateSourceId(templateId: string | null | undefined): string | null {
  if (!templateId?.startsWith(USER_TEMPLATE_PREFIX)) return null;
  return templateId.slice(USER_TEMPLATE_PREFIX.length) || null;
}

export const TEMPLATE_PRESETS: TemplatePreset[] = [
  // 발표 (5)
  {
    id: 'meeting_deck_title',
    category: 'deck',
    mockupId: 'meeting_deck_title',
    preset: {
      use_case: 'meeting_deck',
      style: { chips: ['corporate', 'swiss'], palette: 'brand', background: 'white', quality: 'high' },
      layout: { layout_id: 'left_text_right_visual', aspect: '1536x1024' },
    },
  },
  {
    id: 'meeting_deck_kpi',
    category: 'deck',
    mockupId: 'meeting_deck_kpi',
    preset: {
      use_case: 'status_report',
      style: { chips: ['corporate', 'infographic'], palette: 'brand', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },
  {
    id: 'meeting_deck_compare',
    category: 'deck',
    mockupId: 'meeting_deck_compare',
    preset: {
      use_case: 'comparison',
      style: { chips: ['corporate', 'swiss'], palette: 'brand', background: 'white', quality: 'high' },
      layout: { layout_id: 'two_row_comparison', aspect: '1536x1024' },
    },
  },
  {
    id: 'team_intro',
    category: 'deck',
    mockupId: 'team_intro',
    preset: {
      use_case: 'meeting_deck',
      style: { chips: ['flat', 'corporate'], palette: 'warm', background: 'white', quality: 'high' },
      layout: { layout_id: 'three_column', aspect: '1536x1024' },
    },
  },
  {
    id: 'deck_section_divider',
    category: 'deck',
    mockupId: 'deck_section_divider',
    preset: {
      use_case: 'meeting_deck',
      style: { chips: ['mono', 'swiss'], palette: 'monochrome', background: 'dark', quality: 'high' },
      layout: { layout_id: 'single_focus', aspect: '1536x1024' },
    },
  },

  // 보고서 (4)
  {
    id: 'status_report',
    category: 'report',
    mockupId: 'status_report',
    preset: {
      use_case: 'status_report',
      style: { chips: ['corporate', 'infographic'], palette: 'brand', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },
  {
    id: 'kpi_dashboard',
    category: 'report',
    mockupId: 'kpi_dashboard',
    preset: {
      use_case: 'status_report',
      style: { chips: ['infographic', 'corporate'], palette: 'vivid', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },
  {
    id: 'post_mortem',
    category: 'report',
    mockupId: 'post_mortem',
    preset: {
      use_case: 'status_report',
      style: { chips: ['corporate', 'magazine'], palette: 'cool', background: 'white', quality: 'high' },
      layout: { layout_id: 'three_column', aspect: '1536x1024' },
    },
  },
  {
    id: 'weekly_brief',
    category: 'report',
    mockupId: 'weekly_brief',
    preset: {
      use_case: 'status_report',
      style: { chips: ['magazine', 'corporate'], palette: 'auto', background: 'white', quality: 'high' },
      layout: { layout_id: 'left_text_right_visual', aspect: '1536x1024' },
    },
  },

  // 다이어그램 (5)
  {
    id: 'process_flow',
    category: 'diagram',
    mockupId: 'process_flow',
    preset: {
      use_case: 'process_flow',
      style: { chips: ['flow', 'wireframe'], palette: 'cool', background: 'white', quality: 'high' },
      layout: { layout_id: 'timeline_horizontal', aspect: '1536x1024' },
    },
  },
  {
    id: 'swimlane',
    category: 'diagram',
    mockupId: 'swimlane',
    preset: {
      use_case: 'process_flow',
      style: { chips: ['flow', 'wireframe'], palette: 'cool', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },
  {
    id: 'org_chart',
    category: 'diagram',
    mockupId: 'org_chart',
    preset: {
      use_case: 'process_flow',
      style: { chips: ['orgchart', 'corporate'], palette: 'brand', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },
  {
    id: 'mindmap',
    category: 'diagram',
    mockupId: 'mindmap',
    preset: {
      use_case: 'process_flow',
      style: { chips: ['mindmap', 'doodle'], palette: 'vivid', background: 'white', quality: 'high' },
      layout: { layout_id: 'freeform', aspect: '1536x1024' },
    },
  },
  {
    id: 'data_pipeline',
    category: 'diagram',
    mockupId: 'data_pipeline',
    preset: {
      use_case: 'process_flow',
      style: { chips: ['isometric', 'flow'], palette: 'cool', background: 'white', quality: 'high' },
      layout: { layout_id: 'timeline_horizontal', aspect: '1536x1024' },
    },
  },

  // 카드·배너 (4)
  {
    id: 'quote_card',
    category: 'card',
    mockupId: 'quote_card',
    preset: {
      use_case: 'quote_card',
      style: { chips: ['magazine', 'mono'], palette: 'monochrome', background: 'white', quality: 'high' },
      layout: { layout_id: 'single_focus', aspect: '1024x1024' },
    },
  },
  {
    id: 'announce_card',
    category: 'card',
    mockupId: 'announce_card',
    preset: {
      use_case: 'quote_card',
      style: { chips: ['flat', 'comic'], palette: 'vivid', background: 'dark', quality: 'high' },
      layout: { layout_id: 'single_focus', aspect: '1024x1024' },
    },
  },
  {
    id: 'badge_celebrate',
    category: 'card',
    mockupId: 'badge_celebrate',
    preset: {
      use_case: 'quote_card',
      style: { chips: ['flat', 'kawaii'], palette: 'warm', background: 'white', quality: 'high' },
      layout: { layout_id: 'single_focus', aspect: '1024x1024' },
    },
  },
  {
    id: 'doc_hero',
    category: 'card',
    mockupId: 'doc_hero',
    preset: {
      use_case: 'docs_hero',
      style: { chips: ['watercolor', 'magazine'], palette: 'cool', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },

  // 소셜 (4)
  {
    id: 'blog_header',
    category: 'social',
    mockupId: 'blog_header',
    preset: {
      use_case: 'social_header',
      style: { chips: ['magazine', 'flat'], palette: 'warm', background: 'white', quality: 'high' },
      layout: { layout_id: 'left_text_right_visual', aspect: '1536x1024' },
    },
  },
  {
    id: 'slack_announcement',
    category: 'social',
    mockupId: 'slack_announcement',
    preset: {
      use_case: 'social_header',
      style: { chips: ['flat', 'corporate'], palette: 'auto', background: 'white', quality: 'high' },
      layout: { layout_id: 'single_focus', aspect: '1024x1024' },
    },
  },
  {
    id: 'social_square',
    category: 'social',
    mockupId: 'social_square',
    preset: {
      use_case: 'social_header',
      style: { chips: ['flat', 'risograph'], palette: 'vivid', background: 'white', quality: 'high' },
      layout: { layout_id: 'single_focus', aspect: '1024x1024' },
    },
  },
  {
    id: 'newsletter_top',
    category: 'social',
    mockupId: 'newsletter_top',
    preset: {
      use_case: 'social_header',
      style: { chips: ['magazine', 'newspaper'], palette: 'monochrome', background: 'white', quality: 'high' },
      layout: { layout_id: 'top_title_grid', aspect: '1536x1024' },
    },
  },
];

export function getTemplate(id: string | null | undefined): TemplatePreset | null {
  if (!id) return null;
  return TEMPLATE_PRESETS.find((preset) => preset.id === id) ?? null;
}

export const TEMPLATES_BY_CATEGORY: Record<TemplateCategoryId, TemplatePreset[]> =
  TEMPLATE_CATEGORIES.reduce(
    (acc, cat) => {
      acc[cat] = TEMPLATE_PRESETS.filter((preset) => preset.category === cat);
      return acc;
    },
    {} as Record<TemplateCategoryId, TemplatePreset[]>,
  );
