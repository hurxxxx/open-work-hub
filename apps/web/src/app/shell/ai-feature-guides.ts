export type FeatureGuideToolIds = ReadonlySet<string>;

export const EMPTY_FEATURE_GUIDE_TOOL_IDS: FeatureGuideToolIds = new Set();

export function hasAiFeatureGuide(
  toolId: string | undefined,
  featureGuideToolIds: FeatureGuideToolIds,
): toolId is string {
  return Boolean(toolId) && featureGuideToolIds.has(toolId as string);
}

export function getAiFeatureGuideSrc(toolId: string): string {
  return `/help/ai/${toolId}.html`;
}

export function getAiFeatureGuideTitleKey(toolId: string): string {
  return `shell:nav.${toolId}`;
}
