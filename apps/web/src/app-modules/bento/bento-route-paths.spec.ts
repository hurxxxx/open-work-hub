import { describe, expect, it } from 'vitest';

import {
  buildBentoHubPath,
  buildBentoPresentationPath,
} from './bento-route-paths';

describe('bento route paths', () => {
  it('builds the workspace hub from the generated route contract', () => {
    expect(buildBentoHubPath('team alpha')).toBe(
      '/apps/bento/workspaces/team%20alpha',
    );
  });

  it('keeps presentation links on the canonical presentations route', () => {
    expect(buildBentoPresentationPath('team alpha', 'deck/one')).toBe(
      '/apps/bento/workspaces/team%20alpha/presentations/deck%2Fone',
    );
  });
});
