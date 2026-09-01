import {
  WebSocketTerminalSurface,
  type TerminalConnectionState,
} from '@/src/components/terminal/WebSocketTerminalSurface';
import { agentTerminalWebSocketUrl } from '../api/agent-terminal-api';
import {
  shouldReconnectTerminalSocket,
  terminalReconnectDelayMs,
} from './terminal-reconnect-policy';

export function AgentTerminalSurface({
  ariaLabel,
  onConnectionStateChange,
  onError,
  onExit,
  sessionId,
  token,
}: {
  ariaLabel: string;
  onConnectionStateChange: (state: TerminalConnectionState) => void;
  onError: () => void;
  onExit: () => void;
  sessionId: string;
  token: string;
}) {
  return (
    <WebSocketTerminalSurface
      ariaLabel={ariaLabel}
      onConnectionStateChange={onConnectionStateChange}
      onError={onError}
      onExit={onExit}
      reconnectDelayMs={terminalReconnectDelayMs}
      remoteScroll
      shouldReconnect={shouldReconnectTerminalSocket}
      token={token}
      webSocketUrl={agentTerminalWebSocketUrl(sessionId)}
    />
  );
}
