import type { KeywordSearchEntityType } from '@/src/platform/search/search-api';

export type SearchEntityOption = {
  id: KeywordSearchEntityType | null;
  label: string;
};

export type SearchEntityDescriptorLabel = {
  label: string;
  label_key: string;
};

export function resolveSearchEntityLabel(
  descriptor: SearchEntityDescriptorLabel,
  t: (key: string, options: { defaultValue: string }) => string,
): string {
  return t(descriptor.label_key, { defaultValue: descriptor.label });
}

export function buildSearchEntityLabelMap(
  options: readonly SearchEntityOption[],
): ReadonlyMap<KeywordSearchEntityType, string> {
  return new Map(
    options
      .filter(
        (
          option,
        ): option is SearchEntityOption & { id: KeywordSearchEntityType } =>
          option.id !== null,
      )
      .map((option) => [option.id, option.label]),
  );
}

export function buildWorkspaceSearchSubtitle({
  entityTypeLabels,
  fallback,
  workspaceName,
}: {
  entityTypeLabels: ReadonlyMap<KeywordSearchEntityType, string>;
  fallback: string;
  workspaceName: string;
}): string {
  const segments = [workspaceName.trim(), ...entityTypeLabels.values()].filter(
    Boolean,
  );
  return segments.length > 0 ? segments.join(' · ') : fallback;
}
