import type { CalendarEvent } from '@/src/platform/calendar/calendar-types';

import {
  getPlannerCalendarDropPolicy,
  getPlannerCalendarResizePolicy,
  type PlannerCalendarScheduleCommand,
  type PlannerCalendarScheduleRejectReason,
} from './planner-calendar-schedule-policy';

type PlannerEventScheduleCommand = Extract<
  PlannerCalendarScheduleCommand,
  { type: 'updatePlannerEvent' }
>;
type MeetingScheduleCommand = Extract<
  PlannerCalendarScheduleCommand,
  { type: 'updateMeeting' }
>;
type TaskScheduleCommand = Extract<
  PlannerCalendarScheduleCommand,
  { type: 'updateTask' }
>;

export interface PlannerCalendarScheduleAdapters {
  updatePlannerEvent(
    token: string,
    eventId: string,
    payload: PlannerEventScheduleCommand['payload'],
  ): Promise<unknown>;
  updateMeeting(
    token: string,
    meetingId: string,
    payload: MeetingScheduleCommand['payload'],
  ): Promise<unknown>;
  updateTask(
    token: string,
    taskId: string,
    payload: TaskScheduleCommand['payload'],
  ): Promise<unknown>;
}

export interface PlannerCalendarScheduleMessages {
  meetingAllDayDisallowed: string;
  taskAllDayOnly: string;
  eventMoveFailed: string;
  meetingMoveFailed: string;
  taskScheduleMoveFailed: string;
}

export interface PlannerCalendarScheduleWorkflowOptions {
  token: string | null;
  adapters: PlannerCalendarScheduleAdapters;
  messages: PlannerCalendarScheduleMessages;
  refresh: () => void;
  setActionError: (message: string) => void;
}

export interface PlannerCalendarScheduleWorkflow {
  drop(
    event: CalendarEvent,
    newStartIso: string,
    newEndIso: string,
    newAllDay: boolean,
    revert: () => void,
  ): Promise<void>;
  resize(
    event: CalendarEvent,
    newEndIso: string,
    revert: () => void,
  ): Promise<void>;
}

function getScheduleRejectErrorMessage(
  reason: PlannerCalendarScheduleRejectReason,
  messages: PlannerCalendarScheduleMessages,
): string | null {
  if (reason === 'meetingAllDayDisallowed')
    return messages.meetingAllDayDisallowed;
  if (reason === 'taskAllDayOnly') return messages.taskAllDayOnly;
  return null;
}

function getScheduleCommandErrorMessage(
  command: PlannerCalendarScheduleCommand,
  err: unknown,
  messages: PlannerCalendarScheduleMessages,
): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (command.type === 'updatePlannerEvent') {
    return messages.eventMoveFailed;
  }
  if (command.type === 'updateMeeting') {
    return messages.meetingMoveFailed;
  }
  return messages.taskScheduleMoveFailed;
}

async function runScheduleCommand(
  command: PlannerCalendarScheduleCommand,
  authToken: string,
  adapters: PlannerCalendarScheduleAdapters,
): Promise<void> {
  if (command.type === 'updatePlannerEvent') {
    await adapters.updatePlannerEvent(
      authToken,
      command.sourceId,
      command.payload,
    );
    return;
  }

  if (command.type === 'updateMeeting') {
    await adapters.updateMeeting(authToken, command.sourceId, command.payload);
    return;
  }

  await adapters.updateTask(authToken, command.sourceId, command.payload);
}

async function commitScheduleCommand(
  command: PlannerCalendarScheduleCommand,
  options: PlannerCalendarScheduleWorkflowOptions,
  revert: () => void,
): Promise<void> {
  if (!options.token) {
    revert();
    return;
  }

  try {
    await runScheduleCommand(command, options.token, options.adapters);
    options.refresh();
  } catch (err) {
    revert();
    options.setActionError(
      getScheduleCommandErrorMessage(command, err, options.messages),
    );
  }
}

function rejectScheduleChange(
  reason: PlannerCalendarScheduleRejectReason,
  options: PlannerCalendarScheduleWorkflowOptions,
  revert: () => void,
): void {
  revert();
  const message = getScheduleRejectErrorMessage(reason, options.messages);
  if (message) {
    options.setActionError(message);
  }
}

export function createPlannerCalendarScheduleWorkflow(
  options: PlannerCalendarScheduleWorkflowOptions,
): PlannerCalendarScheduleWorkflow {
  return {
    async drop(event, newStartIso, newEndIso, newAllDay, revert) {
      if (!options.token) {
        revert();
        return;
      }

      const policy = getPlannerCalendarDropPolicy(
        event,
        newStartIso,
        newEndIso,
        newAllDay,
      );
      if (policy.status === 'reject') {
        rejectScheduleChange(policy.reason, options, revert);
        return;
      }

      await commitScheduleCommand(policy.command, options, revert);
    },

    async resize(event, newEndIso, revert) {
      if (!options.token) {
        revert();
        return;
      }

      const policy = getPlannerCalendarResizePolicy(event, newEndIso);
      if (policy.status === 'reject') {
        rejectScheduleChange(policy.reason, options, revert);
        return;
      }

      await commitScheduleCommand(policy.command, options, revert);
    },
  };
}
