import type {
  AiBackendMode,
  LlmHealthResponse,
} from '../../api/ai-api';
import { RoutingStatusIcon } from './RoutingStatusIcon';

interface ChatTopBarProps {
  title: string;
  backendMode: AiBackendMode;
  health: LlmHealthResponse | null;
  healthError: string | null;
}

/**
 * Claude.ai-style minimal header: just the conversation title (left) and a
 * small routing status indicator (right). The actual model picker and scope
 * picker live inside the composer card below — not here — so the header
 * stays calm and the controls are right where the user is typing.
 */
export function ChatTopBar(props: ChatTopBarProps) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-app-border px-4">
      <h1 className="app-text-control text-app-ink">{props.title}</h1>
      <RoutingStatusIcon
        backendMode={props.backendMode}
        health={props.health}
        healthError={props.healthError}
      />
    </header>
  );
}
