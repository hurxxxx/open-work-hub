import { describe, expect, it } from 'vitest';

import { compileFeatureModuleRegistry } from '@/src/app/shell/feature-module-registry';
import { resources } from '@/src/platform/i18n/resources';
import { patentPriorArtManifest, patentPriorArtModule } from './manifest';

describe('patent prior art feature module', () => {
  it('declares a workspace-scoped platform contract', () => {
    expect(patentPriorArtManifest).toMatchObject({
      moduleKind: 'feature',
      moduleId: 'patent-prior-art',
      contract: {
        owner: 'business-app',
        apiDomain: 'patent_prior_art',
        resourceScope: 'workspace',
        workspaceApiPrefixes: ['/api/v1/patent-prior-art'],
        appLocalTests: expect.arrayContaining([
          'apps/api/tests/test_patent_prior_art.py',
          'apps/api/tests/test_patent_prior_art_pipeline.py',
          'apps/api/tests/test_patent_prior_art_scaffold.py',
          'apps/web/src/app-modules/patent-prior-art/api/patent-prior-art-api.spec.ts',
          'apps/web/src/app-modules/patent-prior-art/components/PlanChipEditor.spec.tsx',
          'apps/web/src/app-modules/patent-prior-art/controller/job-poll-coordinator.spec.ts',
          'apps/web/src/app-modules/patent-prior-art/controller/usePatentPriorArtController.spec.ts',
          'apps/web/src/app-modules/patent-prior-art/manifest.spec.ts',
          'apps/web/src/app-modules/patent-prior-art/model/patent-prior-art-view-model.spec.ts',
          'apps/worker/tests/apps/patent_prior_art/test_task.py',
        ]),
      },
    });
    expect(patentPriorArtModule.manifest).toBe(patentPriorArtManifest);
  });

  it('compiles an app-local Patent route without frontend visibility flags', () => {
    const registry = compileFeatureModuleRegistry([patentPriorArtModule]);

    expect(registry.shellRegistrations).toMatchObject([
      {
        appId: 'patent-prior-art',
        navItem: {
          id: 'patent-prior-art',
          category: 'Patent',
        },
        toolRoute: {
          id: 'patent-prior-art.main',
          path: '/w/:workspaceSlug/patent-prior-art',
          subSidebar: 'hidden',
          toolIds: ['patent-prior-art'],
        },
      },
    ]);
    expect(patentPriorArtModule.shell?.navItem).not.toHaveProperty(
      'comingSoon',
    );
  });

  it('provides generic Korean and English workflow and workload copy', () => {
    for (const locale of ['ko-KR', 'en-US'] as const) {
      const appCopy = resources[locale].apps.ai.patentPriorArt;
      const workloadCatalog =
        resources[locale].apps.admin.console.aiSecurity.modelSettings
          .workloadCatalog;
      const copy = {
        appCopy,
        candidateAssessment: workloadCatalog.patentPriorArtCandidateAssessment,
        searchPlan: workloadCatalog.patentPriorArtSearchPlan,
      };

      expect(appCopy).toMatchObject({
        categories: {
          vehicle: {
            description: expect.any(String),
            label: expect.any(String),
          },
        },
        jurisdictions: {
          CN: expect.any(String),
          EP: expect.any(String),
          JP: expect.any(String),
          KR: expect.any(String),
          US: expect.any(String),
          WO: expect.any(String),
        },
        input: {
          description: expect.any(String),
          title: expect.any(String),
        },
        plan: {
          description: expect.any(String),
          title: expect.any(String),
          valueLimit: expect.any(String),
        },
        policy: {
          externalProcessing: expect.any(String),
        },
        reports: {
          description: expect.any(String),
          docx: expect.any(String),
          html: expect.any(String),
          pdf: expect.any(String),
          summary_docx: expect.any(String),
          summary_pdf: expect.any(String),
          title: expect.any(String),
        },
        results: {
          candidates: expect.any(String),
          report: expect.any(String),
        },
        subtitle: expect.any(String),
        title: expect.any(String),
      });
      expect(copy.candidateAssessment).toMatchObject({
        description: expect.any(String),
        label: expect.any(String),
      });
      expect(copy.searchPlan).toMatchObject({
        description: expect.any(String),
        label: expect.any(String),
      });
    }
  });
});
