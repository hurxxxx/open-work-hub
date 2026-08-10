import { describe, expect, it } from 'vitest';

import {
  buildPptAssistantJobPath,
  buildPptAssistantPath,
} from './ppt-assistant-paths';
import { pptAssistantManifest } from './manifest';

describe('PPT assistant paths', () => {
  it('uses the app-owned workspace route instead of the legacy business route', () => {
    const appId = pptAssistantManifest.moduleId;

    expect(buildPptAssistantPath(appId, 'hq')).toBe('/w/hq/ppt-assistant');
    expect(buildPptAssistantJobPath(appId, 'hq', 'job / 1')).toBe(
      '/w/hq/ppt-assistant/jobs/job%20%2F%201',
    );
    expect(buildPptAssistantJobPath(appId, 'hq', 'job-1')).not.toContain(
      '/business/',
    );
  });
});
