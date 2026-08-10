import type {
  MeetingCreateInput,
  MeetingDetail,
  MeetingUpdateInput,
} from '../../api/meeting-api';
import {
  buildCreateMeetingPayload,
  buildUpdateMeetingPayload,
  isEndAfterStart,
  summarizeFileUploadResults,
  type MeetingCreateState,
  type MeetingEditState,
} from './meeting-form-model';

export interface MeetingFormSubmissionPorts {
  createMeeting: (
    token: string,
    workspaceSlug: string,
    payload: MeetingCreateInput,
  ) => Promise<MeetingDetail>;
  updateMeeting: (
    token: string,
    workspaceSlug: string,
    meetingId: string,
    payload: MeetingUpdateInput,
  ) => Promise<MeetingDetail>;
  uploadMeetingFile: (
    token: string,
    workspaceSlug: string,
    meetingId: string,
    file: File,
  ) => Promise<MeetingDetail>;
}

export interface MeetingFormSubmissionMessages {
  endAfterStart: string;
  createFailed: string;
  editFailed: string;
  partialUploadFailed: string;
  fileFailureDefault: string;
  fileFailure: (options: { name: string; message: string }) => string;
}

export type MeetingCreateSubmissionResult =
  | { status: 'validation_failed'; error: string }
  | { status: 'created'; meeting: MeetingDetail }
  | {
      status: 'partial_upload_failed';
      createdMeetingId: string;
      error: string;
      failures: string[];
      remainingFiles: File[];
    }
  | { status: 'failed'; error: string };

export type MeetingEditSubmissionResult =
  | { status: 'validation_failed'; error: string }
  | { status: 'saved'; meeting: MeetingDetail }
  | { status: 'failed'; error: string };

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export async function submitMeetingCreateForm({
  token,
  workspaceSlug,
  state,
  ports,
  messages,
}: {
  token: string;
  workspaceSlug: string;
  state: MeetingCreateState;
  ports: Pick<MeetingFormSubmissionPorts, 'createMeeting' | 'uploadMeetingFile'>;
  messages: MeetingFormSubmissionMessages;
}): Promise<MeetingCreateSubmissionResult> {
  if (!isEndAfterStart(state.startAt, state.endAt)) {
    return { status: 'validation_failed', error: messages.endAfterStart };
  }

  try {
    const meeting = await ports.createMeeting(
      token,
      workspaceSlug,
      buildCreateMeetingPayload(state),
    );

    const uploadResults = await Promise.all(
      state.pickedFiles.map(async (file) => {
        try {
          await ports.uploadMeetingFile(token, workspaceSlug, meeting.id, file);
          return { file, failure: null };
        } catch (error) {
          return {
            file,
            failure: messages.fileFailure({
              name: file.name,
              message: errorMessage(error, messages.fileFailureDefault),
            }),
          };
        }
      }),
    );
    const { failures, remainingFiles } = summarizeFileUploadResults(
      state.pickedFiles,
      uploadResults,
    );

    if (failures.length > 0) {
      return {
        status: 'partial_upload_failed',
        createdMeetingId: meeting.id,
        error: messages.partialUploadFailed,
        failures,
        remainingFiles,
      };
    }

    return { status: 'created', meeting };
  } catch (error) {
    return { status: 'failed', error: errorMessage(error, messages.createFailed) };
  }
}

export async function submitMeetingEditForm({
  token,
  workspaceSlug,
  meetingId,
  state,
  ports,
  messages,
}: {
  token: string;
  workspaceSlug: string;
  meetingId: string;
  state: MeetingEditState;
  ports: Pick<MeetingFormSubmissionPorts, 'updateMeeting'>;
  messages: MeetingFormSubmissionMessages;
}): Promise<MeetingEditSubmissionResult> {
  if (!isEndAfterStart(state.startAt, state.endAt)) {
    return { status: 'validation_failed', error: messages.endAfterStart };
  }

  try {
    const meeting = await ports.updateMeeting(
      token,
      workspaceSlug,
      meetingId,
      buildUpdateMeetingPayload(state),
    );
    return { status: 'saved', meeting };
  } catch (error) {
    return { status: 'failed', error: errorMessage(error, messages.editFailed) };
  }
}
