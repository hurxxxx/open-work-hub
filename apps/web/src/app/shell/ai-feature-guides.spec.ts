import { describe, expect, it } from 'vitest';

import {
  getAiFeatureGuideSrc,
  getAiFeatureGuideTitleKey,
  hasAiFeatureGuide,
} from './ai-feature-guides';

describe('AI feature guides', () => {
  it('uses only the registry projection supplied by the caller', () => {
    const featureGuideToolIds = new Set(['image-wizard']);

    expect(hasAiFeatureGuide('image-wizard', featureGuideToolIds)).toBe(true);
    expect(hasAiFeatureGuide('diagrams', featureGuideToolIds)).toBe(false);
    expect(hasAiFeatureGuide('docs', featureGuideToolIds)).toBe(false);
  });

  it('derives guide metadata from an accepted tool id', () => {
    expect(getAiFeatureGuideSrc('image-wizard')).toBe(
      '/help/ai/image-wizard.html',
    );
    expect(getAiFeatureGuideTitleKey('image-wizard')).toBe(
      'shell:nav.image-wizard',
    );
  });
});
