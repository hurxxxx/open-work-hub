import { describe, expect, it } from 'vitest';

import { isAppEnabled, isNavItemEnabled } from './rag-ui-access';

describe('rag-ui-access', () => {
  it('checks a single app toggle', () => {
    expect(
      isAppEnabled(
        [
          { app_id: 'chatbot', enabled: true },
          { app_id: 'meeting', enabled: false },
        ],
        'chatbot',
      ),
    ).toBe(true);
    expect(
      isAppEnabled(
        [
          { app_id: 'docs', enabled: true },
          { app_id: 'meeting', enabled: false },
        ],
        'meeting',
      ),
    ).toBe(false);
  });

  it('checks a single nav item toggle', () => {
    expect(
      isNavItemEnabled(
        [{ id: 'search' }, { id: 'optional-tool' }],
        'optional-tool',
      ),
    ).toBe(true);
    expect(isNavItemEnabled([{ id: 'search' }], 'optional-tool')).toBe(false);
  });
});
