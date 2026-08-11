import { imageWizardModule } from '@/src/app-modules/image-wizard';
import { retrievalSearchModule } from '@/src/app-modules/retrieval-search';
import { compileFeatureModuleRegistry } from '@/src/app/shell/feature-module-registry';

/**
 * Explicit composition root for the leaf apps surfaced through the business
 * shell. Each entry owns its identity and shell metadata in its local module.
 */
export const businessFeatureModules = [
  imageWizardModule,
  retrievalSearchModule,
] as const;

export const businessFeatureModuleRegistry = compileFeatureModuleRegistry(
  businessFeatureModules,
);

export const businessFeatureShellRegistrations =
  businessFeatureModuleRegistry.shellRegistrations;
