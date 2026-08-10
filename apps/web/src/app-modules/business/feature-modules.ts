import { documentTranslateModule } from '@/src/app-modules/document-translate';
import { draftingModule } from '@/src/app-modules/drafting';
import { emailAssistantModule } from '@/src/app-modules/email-assistant';
import { fmeaCompareModule } from '@/src/app-modules/fmea-compare';
import { imageWizardModule } from '@/src/app-modules/image-wizard';
import { imdsMineralsModule } from '@/src/app-modules/imds-minerals';
import { lawSearchModule } from '@/src/app-modules/law-search';
import { patentAnalysisModule } from '@/src/app-modules/patent-analysis';
import { patentComposeModule } from '@/src/app-modules/patent-compose';
import { patentPriorArtModule } from '@/src/app-modules/patent-prior-art';
import { patentReportModule } from '@/src/app-modules/patent-report';
import { pptAssistantModule } from '@/src/app-modules/ppt-assistant';
import { retrievalSearchModule } from '@/src/app-modules/retrieval-search';
import { specCompareModule } from '@/src/app-modules/spec-compare';
import { compileFeatureModuleRegistry } from '@/src/app/shell/feature-module-registry';

/**
 * Explicit composition root for the leaf apps surfaced through the business
 * shell. Each entry owns its identity and shell metadata in its local module.
 */
export const businessFeatureModules = [
  draftingModule,
  documentTranslateModule,
  specCompareModule,
  fmeaCompareModule,
  imdsMineralsModule,
  imageWizardModule,
  emailAssistantModule,
  pptAssistantModule,
  retrievalSearchModule,
  lawSearchModule,
  patentComposeModule,
  patentAnalysisModule,
  patentReportModule,
  patentPriorArtModule,
] as const;

export const businessFeatureModuleRegistry = compileFeatureModuleRegistry(
  businessFeatureModules,
);

export const businessFeatureShellRegistrations =
  businessFeatureModuleRegistry.shellRegistrations;
