import { documentTranslateModule } from '@/src/app-modules/document-translate';
import { draftingModule } from '@/src/app-modules/drafting';
import { emailAssistantModule } from '@/src/app-modules/email-assistant';
import { imageWizardModule } from '@/src/app-modules/image-wizard';
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
  imageWizardModule,
  emailAssistantModule,
  retrievalSearchModule,
] as const;

export const businessFeatureModuleRegistry = compileFeatureModuleRegistry(
  businessFeatureModules,
);

export const businessFeatureShellRegistrations =
  businessFeatureModuleRegistry.shellRegistrations;
