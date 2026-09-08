import {
  addLocalCalendarDays,
  addNativeDateInputDays,
  formatNativeDateInputValue,
  formatNativeDateTimeInputValue,
  nativeDateTimeInputValueToIso,
  parseNativeDateInputValue,
} from '@/src/platform/time/native-date-input';
import type { PlannerEvent, PlannerEventCreateInput } from '../api/planner-api';
import { defaultTimedRange } from './planner-event-default-time';

export interface PlannerEventModalRange {
  start: Date;
  end: Date;
  allDay: boolean;
}

export interface PlannerEventModalDraft {
  allDay: boolean;
  startDateValue: string;
  startTimeValue: string;
  endDateValue: string;
  endTimeValue: string;
}

export interface PlannerEventModalState {
  loading: boolean;
  saving: boolean;
  deleting: boolean;
  error: string | null;
  title: string;
  description: string;
  location: string;
  allDay: boolean;
  startDateValue: string;
  startTimeValue: string;
  endDateValue: string;
  endTimeValue: string;
}

export type PlannerEventModalAction =
  | { type: 'loadStart' }
  | { type: 'loadSuccess'; event: PlannerEvent }
  | { type: 'loadFailure'; error: string }
  | { type: 'setError'; error: string | null }
  | { type: 'saveStart' }
  | { type: 'saveDone' }
  | { type: 'deleteStart' }
  | { type: 'deleteDone' }
  | { type: 'setTitle'; title: string }
  | { type: 'setDescription'; description: string }
  | { type: 'setLocation'; location: string }
  | { type: 'setStartDateValue'; startDateValue: string }
  | { type: 'setStartTimeValue'; startTimeValue: string }
  | { type: 'setEndDateValue'; endDateValue: string }
  | { type: 'setEndTimeValue'; endTimeValue: string }
  | { type: 'setAllDay'; allDay: boolean };

export const formatDateInputValue = formatNativeDateInputValue;
export const formatDateTimeInputValue = formatNativeDateTimeInputValue;
export const parseLocalDate = parseNativeDateInputValue;
export const addLocalDays = addLocalCalendarDays;

export function incrementYmd(value: string): string {
  return addNativeDateInputDays(value, 1);
}

export function decrementYmd(value: string): string {
  return addNativeDateInputDays(value, -1);
}

function timeInputValueFromDate(value: Date): string {
  return formatDateTimeInputValue(value).slice(11, 16);
}

function dateInputValueFromApiValue(value: string): string {
  return value.includes('T')
    ? formatDateInputValue(new Date(value))
    : value.slice(0, 10);
}

function timeInputValueFromApiValue(value: string, hasTime: boolean): string {
  return hasTime ? timeInputValueFromDate(new Date(value)) : '';
}

function combineDateAndOptionalTime(
  dateValue: string,
  timeValue: string,
): string {
  const normalizedTime = timeValue.trim();
  return normalizedTime
    ? nativeDateTimeInputValueToIso(`${dateValue}T${normalizedTime}`)
    : dateValue;
}

function effectiveStartDateTime(state: PlannerEventModalState): Date | null {
  if (!state.startDateValue) return null;
  if (state.startTimeValue.trim()) {
    return new Date(`${state.startDateValue}T${state.startTimeValue.trim()}`);
  }
  return parseLocalDate(state.startDateValue);
}

function effectiveEndDateTime(state: PlannerEventModalState): Date | null {
  if (!state.endDateValue) return null;
  if (state.endTimeValue.trim()) {
    return new Date(`${state.endDateValue}T${state.endTimeValue.trim()}`);
  }
  const endDate = parseLocalDate(state.endDateValue);
  endDate.setHours(23, 59, 59, 999);
  return endDate;
}

export function buildDraftFromRange(
  range?: PlannerEventModalRange | null,
  now?: Date,
): PlannerEventModalDraft {
  if (range?.allDay) {
    return {
      allDay: true,
      startDateValue: formatDateInputValue(range.start),
      startTimeValue: '',
      endDateValue: decrementYmd(formatDateInputValue(range.end)),
      endTimeValue: '',
    };
  }
  if (range) {
    return {
      allDay: false,
      startDateValue: formatDateInputValue(range.start),
      startTimeValue: timeInputValueFromDate(range.start),
      endDateValue: formatDateInputValue(range.end),
      endTimeValue: timeInputValueFromDate(range.end),
    };
  }
  const fallback = defaultTimedRange(now);
  return {
    allDay: false,
    startDateValue: formatDateInputValue(fallback.start),
    startTimeValue: timeInputValueFromDate(fallback.start),
    endDateValue: formatDateInputValue(fallback.end),
    endTimeValue: timeInputValueFromDate(fallback.end),
  };
}

export function plannerEventToDraft(
  event: PlannerEvent,
): PlannerEventModalDraft {
  if (event.allDay) {
    return {
      allDay: true,
      startDateValue: event.start,
      startTimeValue: '',
      endDateValue: decrementYmd(event.end),
      endTimeValue: '',
    };
  }
  const startHasTime = event.startHasTime ?? event.start.includes('T');
  const endHasTime = event.endHasTime ?? event.end.includes('T');
  return {
    allDay: false,
    startDateValue: dateInputValueFromApiValue(event.start),
    startTimeValue: timeInputValueFromApiValue(event.start, startHasTime),
    endDateValue: dateInputValueFromApiValue(event.end),
    endTimeValue: timeInputValueFromApiValue(event.end, endHasTime),
  };
}

export function plannerEventModalSessionKey(
  eventId: string | null | undefined,
  initialRange: PlannerEventModalRange | null | undefined,
): string {
  if (eventId) {
    return `edit:${eventId}`;
  }
  if (!initialRange) {
    return 'create:default';
  }
  return [
    'create',
    initialRange.allDay ? 'all-day' : 'timed',
    initialRange.start.toISOString(),
    initialRange.end.toISOString(),
  ].join(':');
}

export function initialPlannerEventModalState(
  initialRange: PlannerEventModalRange | null | undefined,
  now?: Date,
): PlannerEventModalState {
  const draft = buildDraftFromRange(initialRange, now);
  return {
    loading: false,
    saving: false,
    deleting: false,
    error: null,
    title: '',
    description: '',
    location: '',
    allDay: draft.allDay,
    startDateValue: draft.startDateValue,
    startTimeValue: draft.startTimeValue,
    endDateValue: draft.endDateValue,
    endTimeValue: draft.endTimeValue,
  };
}

function buildAllDayToggleDraft(
  state: PlannerEventModalState,
  nextAllDay: boolean,
): PlannerEventModalDraft {
  if (nextAllDay === state.allDay) {
    return {
      allDay: state.allDay,
      startDateValue: state.startDateValue,
      startTimeValue: state.startTimeValue,
      endDateValue: state.endDateValue,
      endTimeValue: state.endTimeValue,
    };
  }
  if (nextAllDay) {
    return {
      allDay: true,
      startDateValue: state.startDateValue,
      startTimeValue: '',
      endDateValue: state.endDateValue,
      endTimeValue: '',
    };
  }

  const defaultRange = defaultTimedRange();
  const startDate =
    state.startDateValue || formatDateInputValue(defaultRange.start);
  const endDate = state.endDateValue || startDate;
  return {
    allDay: false,
    startDateValue: startDate,
    startTimeValue:
      state.startTimeValue || timeInputValueFromDate(defaultRange.start),
    endDateValue: endDate,
    endTimeValue:
      state.endTimeValue || timeInputValueFromDate(defaultRange.end),
  };
}

export function plannerEventModalReducer(
  state: PlannerEventModalState,
  action: PlannerEventModalAction,
): PlannerEventModalState {
  switch (action.type) {
    case 'loadStart':
      return { ...state, loading: true, error: null };
    case 'loadSuccess': {
      const eventDraft = plannerEventToDraft(action.event);
      return {
        ...state,
        loading: false,
        title: action.event.title,
        description: action.event.description,
        location: action.event.location,
        allDay: eventDraft.allDay,
        startDateValue: eventDraft.startDateValue,
        startTimeValue: eventDraft.startTimeValue,
        endDateValue: eventDraft.endDateValue,
        endTimeValue: eventDraft.endTimeValue,
      };
    }
    case 'loadFailure':
      return { ...state, loading: false, error: action.error };
    case 'setError':
      return { ...state, error: action.error };
    case 'saveStart':
      return { ...state, saving: true, error: null };
    case 'saveDone':
      return { ...state, saving: false };
    case 'deleteStart':
      return { ...state, deleting: true, error: null };
    case 'deleteDone':
      return { ...state, deleting: false };
    case 'setTitle':
      return { ...state, title: action.title };
    case 'setDescription':
      return { ...state, description: action.description };
    case 'setLocation':
      return { ...state, location: action.location };
    case 'setStartDateValue':
      return { ...state, startDateValue: action.startDateValue };
    case 'setStartTimeValue':
      return { ...state, startTimeValue: action.startTimeValue };
    case 'setEndDateValue':
      return { ...state, endDateValue: action.endDateValue };
    case 'setEndTimeValue':
      return { ...state, endTimeValue: action.endTimeValue };
    case 'setAllDay':
      return { ...state, ...buildAllDayToggleDraft(state, action.allDay) };
    default:
      return state;
  }
}

export function canSave(state: PlannerEventModalState): boolean {
  if (!state.title.trim()) return false;
  if (!state.startDateValue || !state.endDateValue) return false;
  const startDate = parseLocalDate(state.startDateValue);
  const endDate = parseLocalDate(state.endDateValue);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return false;
  }
  if (endDate < startDate) return false;
  if (state.allDay) return true;
  const start = effectiveStartDateTime(state);
  const end = effectiveEndDateTime(state);
  return Boolean(start && end && end > start);
}

export function buildPlannerEventSavePayload(
  state: PlannerEventModalState,
): PlannerEventCreateInput {
  return {
    title: state.title.trim(),
    description: state.description.trim(),
    location: state.location.trim(),
    allDay: state.allDay,
    start: state.allDay
      ? state.startDateValue
      : combineDateAndOptionalTime(state.startDateValue, state.startTimeValue),
    end: state.allDay
      ? incrementYmd(state.endDateValue)
      : combineDateAndOptionalTime(state.endDateValue, state.endTimeValue),
  };
}
