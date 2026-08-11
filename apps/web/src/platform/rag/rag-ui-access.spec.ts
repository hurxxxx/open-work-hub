import { describe, expect, it } from 'vitest';

import {
  isWorkspaceAppEnabled,
  isWorkspaceNavItemEnabled,
} from './rag-ui-access';

describe('rag-ui-access', () => {
  it('checks a single workspace app toggle', () => {
    expect(
      isWorkspaceAppEnabled(
        [
          { app_id: 'chatbot', enabled: true },
          { app_id: 'meeting', enabled: false },
        ],
        'chatbot',
      ),
    ).toBe(true);
    expect(
      isWorkspaceAppEnabled(
        [
          { app_id: 'docs', enabled: true },
          { app_id: 'meeting', enabled: false },
        ],
        'meeting',
      ),
    ).toBe(false);
  });

  it('checks a single workspace nav item toggle', () => {
    expect(
      isWorkspaceNavItemEnabled(
        [{ id: 'search' }, { id: 'optional-tool' }],
        'optional-tool',
      ),
    ).toBe(true);
    expect(isWorkspaceNavItemEnabled([{ id: 'search' }], 'optional-tool')).toBe(
      false,
    );
  });
});
