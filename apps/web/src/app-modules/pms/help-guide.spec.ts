import { describe, expect, it } from 'vitest';

import { getPmsHelpGuideSrc, pmsHelpGuideRegistration } from './help-guide';

describe('PMS help guide locale routing', () => {
  it('opens the Korean guide at the document start', () => {
    expect(getPmsHelpGuideSrc('ko-KR')).toBe(pmsHelpGuideRegistration.src);
  });

  it('opens English users at the English guide section', () => {
    expect(getPmsHelpGuideSrc('en-US')).toBe(
      `${pmsHelpGuideRegistration.src}#english`,
    );
  });

  it('uses the default document when locale is unavailable', () => {
    expect(getPmsHelpGuideSrc(undefined)).toBe(pmsHelpGuideRegistration.src);
  });
});
