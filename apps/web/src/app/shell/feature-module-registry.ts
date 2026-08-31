import type { BackgroundWorkSource } from '@/src/platform/background-work/background-work-session';
import type { FeatureModuleManifest } from './navigation-types';

export type FeatureBackgroundWorkSource = Omit<BackgroundWorkSource, 'appId'>;

export interface FeatureModuleContext<TModuleId extends string = string> {
  appId: TModuleId;
}

export type FeatureBackgroundWorkSourceFactory<
  TModuleId extends string = string,
> = (context: FeatureModuleContext<TModuleId>) => FeatureBackgroundWorkSource;

export interface FeatureModuleRegistration<
  TManifest extends FeatureModuleManifest = FeatureModuleManifest,
> {
  manifest: TManifest;
  /** The registry supplies the manifest identity and owns final appId injection. */
  backgroundWorkSourceFactories?: readonly FeatureBackgroundWorkSourceFactory[];
}

export type FeatureModuleRegistryInput =
  | FeatureModuleManifest
  | FeatureModuleRegistration;

export interface FeatureModuleRegistry {
  aiToolAppIds: readonly string[];
  backgroundWorkSources: readonly BackgroundWorkSource[];
  featureGuideToolIds: readonly string[];
  manifests: readonly FeatureModuleManifest[];
}

export function defineFeatureModule<const TModuleId extends string>(
  manifest: FeatureModuleManifest<TModuleId>,
): FeatureModuleManifest<TModuleId> {
  return manifest;
}

export function defineFeatureModuleRegistration<
  const TManifest extends FeatureModuleManifest,
>(
  registration: FeatureModuleRegistration<TManifest>,
): FeatureModuleRegistration<TManifest> {
  return registration;
}

function normalizeFeatureModuleRegistration(
  input: FeatureModuleRegistryInput,
): FeatureModuleRegistration {
  return 'manifest' in input ? input : { manifest: input };
}

export function compileFeatureModuleRegistry(
  inputs: readonly FeatureModuleRegistryInput[],
  {
    reservedBackgroundWorkSourceIds = [],
    reservedModuleIds = [],
  }: {
    reservedBackgroundWorkSourceIds?: Iterable<string>;
    reservedModuleIds?: Iterable<string>;
  } = {},
): FeatureModuleRegistry {
  const manifests: FeatureModuleManifest[] = [];
  const backgroundWorkSources: BackgroundWorkSource[] = [];
  const aiToolAppIds: string[] = [];
  const featureGuideToolIds: string[] = [];
  const moduleIds = new Set<string>(reservedModuleIds);
  const sourceIds = new Set<string>(reservedBackgroundWorkSourceIds);

  for (const input of inputs) {
    const registration = normalizeFeatureModuleRegistration(input);
    const { manifest } = registration;
    if (moduleIds.has(manifest.moduleId)) {
      throw new Error(`Duplicate feature module id: ${manifest.moduleId}`);
    }
    moduleIds.add(manifest.moduleId);
    manifests.push(manifest);

    if (manifest.surfaces?.aiToolEntry) {
      aiToolAppIds.push(manifest.moduleId);
    }

    for (const createSource of registration.backgroundWorkSourceFactories ??
      []) {
      const source = createSource({ appId: manifest.moduleId });
      const explicitAppId = (source as BackgroundWorkSource).appId;
      if (explicitAppId) {
        throw new Error(
          `Feature background work source ${source.id} must not declare appId; ` +
            `the registry injects ${manifest.moduleId}`,
        );
      }
      if (sourceIds.has(source.id)) {
        throw new Error(`Duplicate background work source id: ${source.id}`);
      }
      sourceIds.add(source.id);
      backgroundWorkSources.push({
        ...source,
        appId: manifest.moduleId,
      });
    }
  }

  return {
    aiToolAppIds,
    backgroundWorkSources,
    featureGuideToolIds,
    manifests,
  };
}
