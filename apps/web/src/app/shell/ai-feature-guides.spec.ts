import { describe, expect, it } from 'vitest';

import {
  getAiFeatureGuideSrc,
  getAiFeatureGuideTitleKey,
  hasAiFeatureGuide,
} from './ai-feature-guides';

describe('AI feature guides', () => {
  it('uses only the registry projection supplied by the caller', () => {
    const featureGuideToolIds = new Set(['registered-tool']);

    expect(hasAiFeatureGuide('registered-tool', featureGuideToolIds)).toBe(
      true,
    );
    expect(hasAiFeatureGuide('diagrams', featureGuideToolIds)).toBe(false);
    expect(hasAiFeatureGuide('docs', featureGuideToolIds)).toBe(false);
  });

  it('derives guide metadata from an accepted tool id', () => {
    expect(getAiFeatureGuideSrc('registered-tool')).toBe(
      '/help/ai/registered-tool.html',
    );
    expect(getAiFeatureGuideTitleKey('registered-tool')).toBe(
      'shell:nav.registered-tool',
    );
  });
});
