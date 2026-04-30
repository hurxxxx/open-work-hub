import { ApiRequestError, apiFetchJson } from '@/src/platform/api/client';
import { rewriteWorkspaceApiPath } from '@/src/platform/workspaces/workspace-utils';

export type PlannerEventVisibility = 'private' | 'public';

export interface PlannerEvent {
  id: string;
  workspaceId: string;
  ownerId: string;
  ownerName: string;
  title: string;
  description: string;
  location: string;
  visibility: PlannerEventVisibility;
  allDay: boolean;
  start: string;
  end: string;
  createdAt: string;
  updatedAt: string;
}

export interface PlannerEventsResponse {
  items: PlannerEvent[];
}

export interface PlannerEventCreateInput {
  title: string;
  description: string;
  location: string;
  visibility: PlannerEventVisibility;
  allDay: boolean;
  start: string;
  end: string;
}

export interface PlannerEventUpdateInput {
  title?: string;
  description?: string;
  location?: string;
  visibility?: PlannerEventVisibility;
  allDay?: boolean;
  start?: string;
  end?: string;
}

export class PlannerApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'PlannerApiError';
  }
}

async function request<T>(
  path: string,
  token: string,
  workspaceSlug: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetchJson<T>(rewriteWorkspaceApiPath(path, workspaceSlug), token, init);
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw new PlannerApiError(
        error.status,
        error.message || `Planner request failed with ${error.status}.`,
      );
    }
    throw error;
  }
}

export function listPlannerEvents(
  token: string,
  workspaceSlug: string,
  options: { from?: string; to?: string } = {},
): Promise<PlannerEventsResponse> {
  const params = new URLSearchParams();
  if (options.from) params.set('from', options.from);
  if (options.to) params.set('to', options.to);
  const query = params.toString();
  return request<PlannerEventsResponse>(
    `/api/v1/planner/events${query ? `?${query}` : ''}`,
    token,
    workspaceSlug,
  );
}

export function getPlannerEvent(
  token: string,
  workspaceSlug: string,
  eventId: string,
): Promise<PlannerEvent> {
  return request<PlannerEvent>(
    `/api/v1/planner/events/${eventId}`,
    token,
    workspaceSlug,
  );
}

export function createPlannerEvent(
  token: string,
  workspaceSlug: string,
  payload: PlannerEventCreateInput,
): Promise<PlannerEvent> {
  return request<PlannerEvent>(
    '/api/v1/planner/events',
    token,
    workspaceSlug,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function updatePlannerEvent(
  token: string,
  workspaceSlug: string,
  eventId: string,
  payload: PlannerEventUpdateInput,
): Promise<PlannerEvent> {
  return request<PlannerEvent>(
    `/api/v1/planner/events/${eventId}`,
    token,
    workspaceSlug,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deletePlannerEvent(
  token: string,
  workspaceSlug: string,
  eventId: string,
): Promise<void> {
  return request<void>(
    `/api/v1/planner/events/${eventId}`,
    token,
    workspaceSlug,
    {
      method: 'DELETE',
    },
  );
}
