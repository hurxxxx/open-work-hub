import { apiFetchJsonWithMappedError } from '@/src/platform/api/client';

export interface PlannerEvent {
  id: string;
  ownerId: string;
  ownerName: string;
  title: string;
  description: string;
  location: string;
  timeZone: string;
  allDay: boolean;
  startHasTime: boolean;
  endHasTime: boolean;
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
  description?: string;
  location?: string;
  allDay?: boolean;
  start: string;
  end: string;
}

export type PlannerEventUpdateInput = Partial<PlannerEventCreateInput>;

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
  init: RequestInit = {},
): Promise<T> {
  return apiFetchJsonWithMappedError<T>(
    path,
    token,
    init,
    (error) =>
      new PlannerApiError(
        error.status,
        error.message || `Planner request failed with ${error.status}.`,
      ),
  );
}

export function listPlannerEvents(
  token: string,
  optionsOrLegacyWorkspace: { from?: string; to?: string } | string = {},
  legacyOptions: { from?: string; to?: string } = {},
): Promise<PlannerEventsResponse> {
  const options =
    typeof optionsOrLegacyWorkspace === 'string'
      ? legacyOptions
      : optionsOrLegacyWorkspace;
  const params = new URLSearchParams();
  if (options.from) params.set('from', options.from);
  if (options.to) params.set('to', options.to);
  const query = params.toString();
  return request<PlannerEventsResponse>(
    `/api/v1/planner/events${query ? `?${query}` : ''}`,
    token,
  );
}

export function getPlannerEvent(
  token: string,
  eventId: string,
): Promise<PlannerEvent> {
  return request<PlannerEvent>(`/api/v1/planner/events/${eventId}`, token);
}

export function createPlannerEvent(
  token: string,
  payload: PlannerEventCreateInput,
): Promise<PlannerEvent> {
  return request<PlannerEvent>('/api/v1/planner/events', token, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updatePlannerEvent(
  token: string,
  eventId: string,
  payload: PlannerEventUpdateInput,
): Promise<PlannerEvent> {
  return request<PlannerEvent>(`/api/v1/planner/events/${eventId}`, token, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deletePlannerEvent(
  token: string,
  eventId: string,
): Promise<void> {
  return request<void>(`/api/v1/planner/events/${eventId}`, token, {
    method: 'DELETE',
  });
}
