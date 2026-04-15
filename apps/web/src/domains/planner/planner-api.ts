import { rewriteWorkspaceApiPath } from '@/src/domains/workspaces/workspace-utils';

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
  const response = await fetch(rewriteWorkspaceApiPath(path, workspaceSlug), {
    ...init,
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
    cache: 'no-store',
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new PlannerApiError(
      response.status,
      payload?.detail ?? `Planner request failed with ${response.status}.`,
    );
  }
  return payload as T;
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
