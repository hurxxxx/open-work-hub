import { Shield, ShieldAlert } from 'lucide-react';
import { Tooltip } from '@aidoo/ui';
import type {
  AiBackendMode,
  LlmHealthResponse,
} from '@/src/domains/ai/ai-api';

interface RoutingStatusIconProps {
  backendMode: AiBackendMode;
  health: LlmHealthResponse | null;
  healthError: string | null;
}

function buildTooltip(props: RoutingStatusIconProps): string {
  if (props.healthError) {
    return props.healthError;
  }
  if (!props.health) {
    return '풀 상태 확인 중';
  }
  const local = props.health.local.ready
    ? `local: 준비됨 (${props.health.local.canonical_model})`
    : `local: ${props.health.local.status}`;
  const external = props.health.external
    ? props.health.external.ready
      ? 'external: 준비됨'
      : `external: ${props.health.external.status}`
    : 'external: 비활성';
  const mode = props.backendMode === 'local' ? '로컬 고정' : '자동 라우팅';
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
  const healthy = isHealthy(props.health, props.backendMode) && !props.healthError;
  return (
    <Tooltip
      content={
        <span className="whitespace-pre-line">{buildTooltip(props)}</span>
      }
    >
      <button
        aria-label="라우팅 상태"
        className={`flex h-8 w-8 items-center justify-center rounded-full border transition-colors ${
          healthy
            ? 'border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-400'
            : 'border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-500'
        }`}
        type="button"
      >
        {healthy ? <Shield size={14} /> : <ShieldAlert size={14} />}
      </button>
    </Tooltip>
  );
}
