import { Shield, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip } from '@ai-do/ui';
import type { AiBackendMode, LlmHealthResponse } from '../../api/chatbot-api';

interface RoutingStatusIconProps {
  backendMode: AiBackendMode;
  health: LlmHealthResponse | null;
  healthError: string | null;
}

function buildTooltip(
  props: RoutingStatusIconProps,
  t: (key: string) => string,
): string {
  if (props.healthError) {
    return props.healthError;
  }
  if (!props.health) {
    return t('ai.routing.checking');
  }
  const local = props.health.local.ready
    ? `local: ${t('ai.routing.ready')} (${props.health.local.canonical_model})`
    : `local: ${props.health.local.status}`;
  const external = props.health.external
    ? props.health.external.ready
      ? `external: ${t('ai.routing.ready')}`
      : `external: ${props.health.external.status}`
    : `external: ${t('ai.routing.inactive')}`;
  const mode =
    props.backendMode === 'local'
      ? t('ai.message.localFixed')
      : t('ai.message.autoRouting');
  return `${mode}\n${local}\n${external}`;
}

// Healthy iff the selected backend mode can actually route a request:
// - `local` mode: only local.ready matters (external is ignored by the backend)
// - `auto` mode: backend uses `local.ready || external.ready` (llm.py LlmDualHealth.ready)
function isHealthy(
  health: LlmHealthResponse | null,
  mode: AiBackendMode,
): boolean {
  if (!health) {
    return false;
  }
  if (mode === 'local') {
    return health.local.ready;
  }
  return health.local.ready || Boolean(health.external?.ready);
}

export function RoutingStatusIcon(props: RoutingStatusIconProps) {
  const { t } = useTranslation('apps');
  const healthy =
    isHealthy(props.health, props.backendMode) && !props.healthError;
  const accessibleStatus = healthy
    ? t('ai.routing.ready')
    : t('ai.routing.unavailable');
  return (
    <Tooltip
      content={
        <span className="whitespace-pre-line">{buildTooltip(props, t)}</span>
      }
    >
      <button
        aria-label={`${t('ai.routing.status')}: ${accessibleStatus}`}
        className={`flex h-8 w-8 items-center justify-center rounded-full border transition-colors ${
          healthy
            ? 'border-app-success-border bg-app-success-bg text-app-success-text dark:border-app-success-border dark:bg-app-success-bg dark:text-app-success-text'
            : 'border-app-warning-border bg-app-warning-bg text-app-warning-text dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-app-warning'
        }`}
        type="button"
      >
        {healthy ? <Shield size={14} /> : <ShieldAlert size={14} />}
      </button>
    </Tooltip>
  );
}
