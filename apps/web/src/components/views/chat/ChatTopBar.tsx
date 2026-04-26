import type {
  AiBackendMode,
  LlmHealthResponse,
} from '@/src/domains/ai/ai-api';
import { ModelPill } from '@/src/components/views/chat/ModelPill';
import { RoutingStatusIcon } from '@/src/components/views/chat/RoutingStatusIcon';
import {
  ChatScopePicker,
  type ChatScopeOption,
} from '@/src/components/views/chat/ChatScopePicker';

interface ChatTopBarProps {
  title: string;
  backendMode: AiBackendMode;
  onBackendModeChange: (mode: AiBackendMode) => void;
  health: LlmHealthResponse | null;
  healthError: string | null;
  isCheckingHealth: boolean;
  onRefreshHealth: () => void;
  canRefresh: boolean;
  scopeOptions: ChatScopeOption[];
  scopeSelected: string[] | null;
  onScopeChange: (next: string[] | null) => void;
  scopeDisabled?: boolean;
}

export function ChatTopBar(props: ChatTopBarProps) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-app-border px-4">
      <h1 className="app-text-control text-app-ink">{props.title}</h1>
      <div className="flex items-center gap-2">
        {props.scopeOptions.length > 0 ? (
          <ChatScopePicker
            options={props.scopeOptions}
            selected={props.scopeSelected}
            onChange={props.onScopeChange}
            disabled={props.scopeDisabled}
          />
        ) : null}
        <ModelPill
          backendMode={props.backendMode}
          onBackendModeChange={props.onBackendModeChange}
          health={props.health}
          healthError={props.healthError}
          isCheckingHealth={props.isCheckingHealth}
          onRefreshHealth={props.onRefreshHealth}
          canRefresh={props.canRefresh}
        />
        <RoutingStatusIcon
          backendMode={props.backendMode}
          health={props.health}
          healthError={props.healthError}
        />
      </div>
    </header>
  );
}
