import {
  TEMPLATES_BY_CATEGORY,
  TEMPLATE_CATEGORIES,
  TEMPLATE_PRESETS,
  type TemplateCategoryId,
  type TemplatePreset,
} from '../templates/template-presets';

export type Step1TemplateCategory = TemplateCategoryId | 'all';

export interface Step1TemplateCategoryOption {
  active: boolean;
  count: number;
  id: Step1TemplateCategory;
  labelKey: string;
}

export interface Step1TemplatesProjection {
  categoryOptions: Step1TemplateCategoryOption[];
  sectionHeadingKey: string;
  showUserTemplates: boolean;
  visibleTemplates: TemplatePreset[];
}

export function buildStep1TemplatesProjection(
  category: Step1TemplateCategory,
  userTemplates: readonly TemplatePreset[],
): Step1TemplatesProjection {
  return {
    categoryOptions: buildStep1TemplateCategoryOptions(category),
    sectionHeadingKey: getStep1TemplateSectionHeadingKey(category),
    showUserTemplates: shouldShowStep1UserTemplates(category, userTemplates),
    visibleTemplates: getVisibleStep1Templates(category),
  };
}

export function buildStep1TemplateCategoryOptions(
  activeCategory: Step1TemplateCategory,
): Step1TemplateCategoryOption[] {
  return [
    {
      id: 'all',
      labelKey: 'ai.imageWizard.gallery.categories.all',
      count: TEMPLATE_PRESETS.length,
      active: activeCategory === 'all',
    },
    ...TEMPLATE_CATEGORIES.map((id) => ({
      id,
      labelKey: `ai.imageWizard.gallery.categories.${id}`,
      count: TEMPLATES_BY_CATEGORY[id].length,
      active: activeCategory === id,
    })),
  ];
}

export function getVisibleStep1Templates(
  category: Step1TemplateCategory,
): TemplatePreset[] {
  if (category === 'all') return TEMPLATE_PRESETS;
  return TEMPLATES_BY_CATEGORY[category] ?? [];
}

export function shouldShowStep1UserTemplates(
  category: Step1TemplateCategory,
  userTemplates: readonly TemplatePreset[],
): boolean {
  return category === 'all' && userTemplates.length > 0;
}

export function getStep1TemplateSectionHeadingKey(
  category: Step1TemplateCategory,
): string {
  return category === 'all'
    ? 'ai.imageWizard.gallery.allHeading'
    : `ai.imageWizard.gallery.categories.${category}`;
}
