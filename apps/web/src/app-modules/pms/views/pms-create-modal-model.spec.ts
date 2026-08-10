import { describe, expect, it } from 'vitest';

import {
  canSubmitCreateName,
  createFolderPayload,
  createTaskListPayload,
  INITIAL_PMS_CREATE_MODAL_STATE,
  pmsCreateModalReducer,
} from './pms-create-modal-model';

describe('pms create modal model', () => {
  it('creates the shared initial modal state', () => {
    expect(INITIAL_PMS_CREATE_MODAL_STATE).toEqual({
      name: '',
      description: '',
      submitting: false,
      error: '',
    });
  });

  it('accepts names with non-whitespace content only', () => {
    expect(canSubmitCreateName('Project folder')).toBe(true);
    expect(canSubmitCreateName('  Project folder  ')).toBe(true);
    expect(canSubmitCreateName('')).toBe(false);
    expect(canSubmitCreateName('   ')).toBe(false);
  });

  it('builds trimmed create folder payloads', () => {
    expect(
      createFolderPayload({
        name: '  Roadmap  ',
        teamId: 'team-1',
      }),
    ).toEqual({
      name: 'Roadmap',
      team_id: 'team-1',
    });
  });

  it('builds trimmed create task list payloads while preserving nullable scope', () => {
    expect(
      createTaskListPayload({
        name: '  Sprint 1  ',
        description: '  Planning work  ',
        teamId: null,
        folderId: 'folder-1',
      }),
    ).toEqual({
      name: 'Sprint 1',
      description: 'Planning work',
      team_id: null,
      folder_id: 'folder-1',
    });
  });

  it('keeps reducer transitions pure across submit, failure, finish, and reset', () => {
    const named = pmsCreateModalReducer(INITIAL_PMS_CREATE_MODAL_STATE, {
      type: 'name',
      value: 'Release',
    });
    const described = pmsCreateModalReducer(named, {
      type: 'description',
      value: 'Notes',
    });
    const submitting = pmsCreateModalReducer(
      { ...described, error: 'Previous failure' },
      { type: 'submit' },
    );
    const failed = pmsCreateModalReducer(submitting, {
      type: 'failed',
      message: 'Could not create',
    });
    const finished = pmsCreateModalReducer(failed, { type: 'finished' });

    expect(described).toMatchObject({
      name: 'Release',
      description: 'Notes',
    });
    expect(submitting).toMatchObject({
      submitting: true,
      error: '',
    });
    expect(failed).toMatchObject({
      submitting: true,
      error: 'Could not create',
    });
    expect(finished.submitting).toBe(false);
    expect(pmsCreateModalReducer(finished, { type: 'reset' })).toBe(
      INITIAL_PMS_CREATE_MODAL_STATE,
    );
  });
});
