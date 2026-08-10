import type {
  AiBackendMode,
  LlmHealthResponse,
  LlmPoolHealthResponse,
} from '../../api/chatbot-api';

export type ModelPillTranslate = (key: string) => string;

export interface BackendOption {
  value: AiBackendMode;
  labelKey: string;
  descriptionKey: string;
}

export interface ProjectedBackendOption extends BackendOption {
  label: string;
  description: string;
  selected: boolean;
  className: string;
}

export const BACKEND_OPTIONS: BackendOption[] = [
  {
    value: 'auto',
    labelKey: 'ai.model.auto',
    descriptionKey: 'ai.model.policyRouting',
  },
  {
    value: 'local',
    labelKey: 'ai.model.local',
    descriptionKey: 'ai.model.localPoolFixed',
  },
];

export function formatPillLabel(
  health: LlmHealthResponse | null,
  mode: AiBackendMode,
  t: ModelPillTranslate,
): string {
  if (!health) {
    return mode === 'local'
      ? t('ai.model.localChecking')
      : t('ai.model.autoChecking');
  }
  if (mode === 'local') {
    return `${health.local.canonical_model} · ${t('ai.model.local')}`;
  }
  return t('ai.message.autoRouting');
}

export function formatBackendStatus(
  health: LlmPoolHealthResponse | null | undefined,
  t: ModelPillTranslate,
): string {
  if (!health) {
    return t('ai.model.notChecked');
  }
  if (health.ready) {
    return t('ai.routing.ready');
  }
  return health.status;
}

export function isRefreshDisabled({
  canRefresh,
  isCheckingHealth,
}: {
  canRefresh: boolean;
  isCheckingHealth: boolean;
}): boolean {
  return !canRefresh || isCheckingHealth;
}

export function projectBackendOption(
  option: BackendOption,
  selectedMode: AiBackendMode,
  t: ModelPillTranslate,
): ProjectedBackendOption {
  const selected = selectedMode === option.value;
  return {
    ...option,
    label: t(option.labelKey),
    description: t(option.descriptionKey),
    selected,
    className: selected
      ? 'border-app-accent bg-app-bg text-app-ink'
      : 'border-app-border bg-app-surface text-app-ink/55 hover:border-app-accent hover:text-app-ink',
  };
}
