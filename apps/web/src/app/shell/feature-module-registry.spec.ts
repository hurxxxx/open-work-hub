import { describe, expect, it } from 'vitest';

import {
  compileFeatureModuleRegistry,
  defineFeatureModule,
  defineFeatureModuleRegistration,
} from './feature-module-registry';

function manifest(moduleId: string) {
  return defineFeatureModule({
    moduleKind: 'feature',
    moduleId,
    contract: {
      owner: `${moduleId}-owner`,
      permissions: [],
      apiDomain: null,
      aiCapabilities: [],
      writeAuditActions: [],
      appLocalTests: [],
    },
  });
}

describe('feature module registry', () => {
  it('injects app identity and projects declared capabilities', async () => {
    const registered = defineFeatureModuleRegistration({
      manifest: {
        ...manifest('custom-tool'),
        contract: manifest('custom-tool').contract,
        surfaces: { aiToolEntry: true },
      },
      backgroundWorkSourceFactories: [
        ({ appId }) => ({
          id: 'custom-jobs',
          list: async () => [
            {
              href: `/jobs/${appId}`,
              id: 'job-1',
              kind: 'custom',
              sourceId: 'custom-jobs',
              status: 'running',
              title: 'Custom job',
              updatedAt: '2026-07-15T00:00:00Z',
            },
          ],
        }),
      ],
    });

    const registry = compileFeatureModuleRegistry([registered]);

    expect(registry.aiToolAppIds).toEqual(['custom-tool']);
    expect(registry.featureGuideToolIds).toEqual([]);
    expect(registry.backgroundWorkSources[0]).toMatchObject({
      appId: 'custom-tool',
      id: 'custom-jobs',
    });
    await expect(
      registry.backgroundWorkSources[0].list({
        token: 'token',
        t: (key) => key,
      }),
    ).resolves.toMatchObject([{ href: '/jobs/custom-tool' }]);
  });

  it('rejects duplicate module and source ids', () => {
    expect(() =>
      compileFeatureModuleRegistry([
        manifest('duplicate'),
        manifest('duplicate'),
      ]),
    ).toThrow('Duplicate feature module id: duplicate');

    expect(() =>
      compileFeatureModuleRegistry([manifest('core-app')], {
        reservedModuleIds: ['core-app'],
      }),
    ).toThrow('Duplicate feature module id: core-app');

    expect(() =>
      compileFeatureModuleRegistry([
        defineFeatureModuleRegistration({
          manifest: manifest('first'),
          backgroundWorkSourceFactories: [
            () => ({ id: 'jobs', list: async () => [] }),
          ],
        }),
        defineFeatureModuleRegistration({
          manifest: manifest('second'),
          backgroundWorkSourceFactories: [
            () => ({ id: 'jobs', list: async () => [] }),
          ],
        }),
      ]),
    ).toThrow('Duplicate background work source id: jobs');

    expect(() =>
      compileFeatureModuleRegistry(
        [
          defineFeatureModuleRegistration({
            manifest: manifest('feature'),
            backgroundWorkSourceFactories: [
              () => ({ id: 'core-jobs', list: async () => [] }),
            ],
          }),
        ],
        { reservedBackgroundWorkSourceIds: ['core-jobs'] },
      ),
    ).toThrow('Duplicate background work source id: core-jobs');
  });

  it('rejects source-owned app ids instead of accepting split identity', () => {
    expect(() =>
      compileFeatureModuleRegistry([
        defineFeatureModuleRegistration({
          manifest: manifest('owner'),
          backgroundWorkSourceFactories: [
            () =>
              ({
                appId: 'other',
                id: 'jobs',
                list: async () => [],
              }) as never,
          ],
        }),
      ]),
    ).toThrow('must not declare appId');
  });
});
