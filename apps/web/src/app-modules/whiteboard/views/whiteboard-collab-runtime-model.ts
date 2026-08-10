import type {
  Collaborator,
  SocketId,
} from '@excalidraw/excalidraw/types';

import { colorForUser, type CollabStatus } from './whiteboard-editor-utils';

export type ActiveWhiteboardCollabStatus = Exclude<CollabStatus, null>;

export interface WhiteboardCollabStatusSnapshot {
  boardId: string;
  status: ActiveWhiteboardCollabStatus;
}

export interface WhiteboardAwarenessUser {
  id: string;
  fullName: string;
  color: string;
}

export interface WhiteboardAwarenessState {
  user?: WhiteboardAwarenessUser;
  cursor?: {
    x: number;
    y: number;
    tool: 'pointer' | 'laser';
  };
  button?: 'down' | 'up';
  selectedElementIds?: Record<string, true>;
}

export function resolveWhiteboardCollabStatus({
  boardId,
  snapshot,
}: {
  boardId: string | null;
  snapshot: WhiteboardCollabStatusSnapshot | null;
}): CollabStatus {
  if (!boardId) return null;
  return snapshot?.boardId === boardId ? snapshot.status : 'connecting';
}

export function resolveWhiteboardProviderStatus(
  status: string | undefined,
): ActiveWhiteboardCollabStatus | null {
  if (status === 'connected') return 'connected';
  if (status === 'connecting') return 'connecting';
  if (status === 'disconnected') return 'offline';
  return null;
}

export function resolveWhiteboardConnectionCloseStatus(
  code: number | undefined,
): ActiveWhiteboardCollabStatus | null {
  if (code === 4403) return 'error';
  if (code === 1011 || code === 1013) return 'offline';
  return null;
}

export function createWhiteboardAwarenessUser({
  fullName,
  id,
}: {
  fullName: string;
  id: string;
}): WhiteboardAwarenessUser {
  return {
    id,
    fullName,
    color: colorForUser(id),
  };
}

export function normalizeWhiteboardSelectedElementIds(
  selectedElementIds: unknown,
): Record<string, unknown> {
  return selectedElementIds && typeof selectedElementIds === 'object'
    ? (selectedElementIds as Record<string, unknown>)
    : {};
}

export function buildWhiteboardCollaborators({
  localClientId,
  states,
}: {
  localClientId: number;
  states: ReadonlyMap<number, unknown>;
}): Map<SocketId, Collaborator> {
  const collaborators = new Map<SocketId, Collaborator>();
  states.forEach((state, clientId) => {
    if (clientId === localClientId) return;
    const awareness = state as WhiteboardAwarenessState;
    const socketId = String(clientId) as SocketId;
    const color = awareness.user?.color ?? colorForUser(socketId);
    collaborators.set(socketId, {
      id: awareness.user?.id ?? socketId,
      socketId,
      username: awareness.user?.fullName ?? 'User',
      pointer: awareness.cursor,
      button: awareness.button,
      selectedElementIds: awareness.selectedElementIds,
      color: {
        stroke: color,
        background: color,
      },
    });
  });
  return collaborators;
}
