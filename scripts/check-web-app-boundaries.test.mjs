import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  collectSpecifiers,
  createBoundaryPaths,
  formatViolations,
  isPlatformModulePath,
  parseAppModulePath,
  runCli,
  runWebAppBoundaryCheck,
} from './check-web-app-boundaries.mjs';

function createTempRepo(t, files) {
  const repoRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'web-boundaries-'));
  fs.mkdirSync(path.join(repoRoot, 'apps/web/src'), { recursive: true });

  for (const [relativePath, source] of Object.entries(files)) {
    const filePath = path.join(repoRoot, relativePath);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, source);
  }

  t.after(() => {
    fs.rmSync(repoRoot, { recursive: true, force: true });
  });

  return repoRoot;
}

test('collectSpecifiers finds static, type, side-effect, export, and dynamic imports', () => {
  const source = `
    import React from 'react';
    import type { DocsApi } from '@/src/app-modules/docs/public-api';
    import '@/src/platform/init';
    export { readDoc } from './read-doc';
    export type { DocSummary } from '../model/doc-summary';
    const lazy = import('@/src/app-modules/pms/manifest');
  `;

  assert.deepEqual(collectSpecifiers(source), [
    'react',
    '@/src/app-modules/docs/public-api',
    '@/src/platform/init',
    './read-doc',
    '../model/doc-summary',
    '@/src/app-modules/pms/manifest',
  ]);
});

test('parseAppModulePath resolves app id and first app-local segment', () => {
  const { appModulesRoot, webSrcRoot } = createBoundaryPaths('/tmp/repo');

  assert.deepEqual(
    parseAppModulePath(path.join(appModulesRoot, 'docs/views/DocsView.tsx'), {
      appModulesRoot,
    }),
    { appId: 'docs', segment: 'views' },
  );
  assert.deepEqual(
    parseAppModulePath(path.join(appModulesRoot, 'docs'), { appModulesRoot }),
    { appId: 'docs', segment: '' },
  );
  assert.equal(
    parseAppModulePath(path.join(webSrcRoot, 'platform/shell.ts'), {
      appModulesRoot,
    }),
    null,
  );
});

test('isPlatformModulePath recognizes web platform files', () => {
  const { webSrcRoot } = createBoundaryPaths('/tmp/repo');

  assert.equal(
    isPlatformModulePath(path.join(webSrcRoot, 'platform/auth/auth-provider.tsx'), {
      webSrcRoot,
    }),
    true,
  );
  assert.equal(
    isPlatformModulePath(path.join(webSrcRoot, 'app/shell/AppContent.tsx'), {
      webSrcRoot,
    }),
    false,
  );
});

test('runWebAppBoundaryCheck allows same-app internals and public app module aliases', (t) => {
  const repoRoot = createTempRepo(t, {
    'apps/web/src/app-modules/docs/views/DocsView.ts': `
      import { docsModel } from '../model/docs-model';
      import { pmsModule } from '@/src/app-modules/pms';
      import { pmsManifest } from '@/src/app-modules/pms/manifest';
      import { pmsApi } from '@/src/app-modules/pms/public-api';
      const lazy = import('@/src/app-modules/pms/public-api');
      export { docsModel };
      export { pmsModule, pmsManifest, pmsApi, lazy };
    `,
    'apps/web/src/app-modules/docs/model/docs-model.ts': `
      export const docsModel = true;
    `,
    'apps/web/src/platform/shell.ts': `
      import { docsApi } from '@/src/app-modules/docs/public-api';
      export { docsApi };
    `,
    'apps/web/src/app-modules/docs/public-api.ts': `
      export const docsApi = true;
    `,
  });

  const result = runWebAppBoundaryCheck(repoRoot);

  assert.equal(result.ok, true);
  assert.deepEqual(result.violations, []);
});

test('runWebAppBoundaryCheck blocks platform modules from importing app module roots', (t) => {
  const repoRoot = createTempRepo(t, {
    'apps/web/src/platform/personal-widgets/PersonalWidgetHost.ts': `
      import { FloatingDmWidget } from '@/src/app-modules/dm';
      import { RelativeFloatingDmWidget } from '../../app-modules/dm';
      import { RelativeFloatingDmIndexWidget } from '../../app-modules/dm/index';
      import { pmsApi } from '@/src/app-modules/pms/public-api';
      export { FloatingDmWidget, RelativeFloatingDmWidget, RelativeFloatingDmIndexWidget, pmsApi };
    `,
    'apps/web/src/app/shell/AppContent.ts': `
      import { dmManifest } from '@/src/app-modules/dm';
      export { dmManifest };
    `,
  });

  const result = runWebAppBoundaryCheck(repoRoot);

  assert.equal(result.ok, false);
  assert.deepEqual(result.violations, [
    {
      file: path.join(
        repoRoot,
        'apps/web/src/platform/personal-widgets/PersonalWidgetHost.ts',
      ),
      specifier: '@/src/app-modules/dm',
      reason:
        'Platform modules must consume feature modules through shell adapters or app public-api, not app module roots.',
    },
    {
      file: path.join(
        repoRoot,
        'apps/web/src/platform/personal-widgets/PersonalWidgetHost.ts',
      ),
      specifier: '../../app-modules/dm',
      reason:
        'Platform modules must consume feature modules through shell adapters or app public-api, not app module roots.',
    },
    {
      file: path.join(
        repoRoot,
        'apps/web/src/platform/personal-widgets/PersonalWidgetHost.ts',
      ),
      specifier: '../../app-modules/dm/index',
      reason:
        'Platform modules must consume feature modules through shell adapters or app public-api, not app module roots.',
    },
  ]);
});

test('runWebAppBoundaryCheck reports forbidden app boundary imports', (t) => {
  const repoRoot = createTempRepo(t, {
    'apps/web/src/app-modules/docs/views/DocsView.ts': `
      import { PmsView } from '../../pms/views/PMSView';
      import { legacyDomain } from '@/src/domains/legacy';
      import { privatePms } from '@/src/app-modules/pms/views/PMSView';
      const view = import('@/src/components/views/LegacyView');
      export { PmsView, legacyDomain, privatePms, view };
    `,
    'apps/web/src/platform/shell.ts': `
      import { DocsView } from '../app-modules/docs/views/DocsView';
      export { DocsView };
    `,
  });

  const result = runWebAppBoundaryCheck(repoRoot);
  const reasons = result.violations.map((violation) => violation.reason);

  assert.equal(result.ok, false);
  assert.ok(
    reasons.includes(
      'Cross-app imports must go through the shell registry/public app boundary, not docs to pms.',
    ),
  );
  assert.ok(
    reasons.includes(
      'Legacy domains imports are closed. Use platform/* or app-modules/<appId> public/internal boundaries.',
    ),
  );
  assert.ok(
    reasons.includes(
      'Import app modules through their public module root or manifest boundary only.',
    ),
  );
  assert.ok(
    reasons.includes(
      'App-specific views must live inside app-modules/<appId>/views, not shared components/views.',
    ),
  );
  assert.ok(
    reasons.includes('Outside app-modules cannot import docs/views internals.'),
  );
});

test('formatViolations preserves the CLI violation message shape', (t) => {
  const repoRoot = createTempRepo(t, {
    'apps/web/src/app-modules/docs/views/DocsView.ts': `
      import { PmsView } from '../../pms/views/PMSView';
      export { PmsView };
    `,
  });
  const result = runWebAppBoundaryCheck(repoRoot);

  assert.equal(
    formatViolations(result.violations, repoRoot),
    [
      'Web app boundary violations found:',
      '',
      '- apps/web/src/app-modules/docs/views/DocsView.ts imports "../../pms/views/PMSView"',
      '  Cross-app imports must go through the shell registry/public app boundary, not docs to pms.',
    ].join('\n'),
  );
});

test('runCli returns the existing success output and failure exit code', (t) => {
  const passingRepoRoot = createTempRepo(t, {
    'apps/web/src/app-modules/docs/public-api.ts': `
      export const docsApi = true;
    `,
  });
  const failingRepoRoot = createTempRepo(t, {
    'apps/web/src/app-modules/docs/views/DocsView.ts': `
      import { privatePms } from '@/src/app-modules/pms/views/PMSView';
      export { privatePms };
    `,
  });
  const stdout = [];
  const stderr = [];

  assert.equal(
    runCli({
      cwd: passingRepoRoot,
      stdout: (message) => stdout.push(message),
      stderr: (message) => stderr.push(message),
    }),
    0,
  );
  assert.deepEqual(stdout, ['Web app module boundaries OK']);

  assert.equal(
    runCli({
      cwd: failingRepoRoot,
      stdout: (message) => stdout.push(message),
      stderr: (message) => stderr.push(message),
    }),
    1,
  );
  assert.match(stderr[0], /^Web app boundary violations found:\n\n-/);
});
