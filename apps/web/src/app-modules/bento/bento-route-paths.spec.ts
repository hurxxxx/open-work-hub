import { describe, expect, it } from 'vitest';

import {
  buildBentoHubPath,
  buildBentoPresentationPath,
} from './bento-route-paths';

describe('bento route paths', () => {
  it('builds the workspace hub from the generated route contract', () => {
    expect(buildBentoHubPath()).toBe('/apps/bento');
  });

  it('keeps presentation links on the canonical presentations route', () => {
    expect(buildBentoPresentationPath('deck/one')).toBe(
      '/apps/bento/presentations/deck%2Fone',
    );
  });
});
