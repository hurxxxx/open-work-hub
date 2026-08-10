import { describe, expect, it } from 'vitest';

import {
  getAiFeatureGuideSrc,
  getAiFeatureGuideTitleKey,
  hasAiFeatureGuide,
} from './ai-feature-guides';

describe('AI feature guides', () => {
  it('uses only the registry projection supplied by the caller', () => {
    const featureGuideToolIds = new Set(['drafting']);

    expect(hasAiFeatureGuide('drafting', featureGuideToolIds)).toBe(true);
    expect(hasAiFeatureGuide('diagrams', featureGuideToolIds)).toBe(false);
    expect(hasAiFeatureGuide('docs', featureGuideToolIds)).toBe(false);
  });

  it('derives guide metadata from an accepted tool id', () => {
    expect(getAiFeatureGuideSrc('drafting')).toBe('/help/ai/drafting.html');
    expect(getAiFeatureGuideTitleKey('drafting')).toBe('shell:nav.drafting');
  });
});
