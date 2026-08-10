import { fireEvent, render, screen, within } from '@testing-library/react';
import { createElement } from 'react';
import { describe, expect, it, vi } from 'vitest';

import {
  LEGACY_ISSUE_DEFAULT_VIEW_KEY,
  LEGACY_ISSUE_VIEWS,
} from '../legacy-issue-datasets';
import type {
  LegacyIssueDatasetDefinition,
  LegacyIssueDatasetField,
  LegacyIssueDatasetRecord,
  LegacyIssueRevision,
  LegacyIssueRevisionOverviewHistory,
} from '../api/legacy-issue-api';
import {
  applyPendingDraftChangesToLoadedRecords,
  buildLegacyIssueBlankRowDefaultValues,
  buildLegacyIssueDraftChangedCellKeys,
  buildLegacyIssueRevisionOverviewRows,
  buildLegacyIssueDraftBatchPayload,
  canApplyLegacyIssueInlineCellEdits,
  canEditLegacyIssueDraftRevision,
  canForceCancelLegacyIssueDraftRevision,
  canDirectEditLegacyIssuePublishedRevision,
  canEditLegacyIssueRevisionAssignee,
  canEditLegacyIssueAttachmentsInRevision,
  countLegacyIssuePendingDraftChanges,
  countPendingAttachmentEdits,
  displayLegacyIssueRevisionSummary,
  isValidOverviewHistoryDraft,
  isLegacyIssueRevisionAssigneeChangeBlocked,
  isLegacyIssueRevisionReadyToPublish,
  legacyIssueMainTabSearchParams,
  legacyIssueReferenceKindForField,
  mapLegacyIssueCreatedRecordsByClientId,
  mergeLegacyIssueRecordValues,
  mergePendingRecordEditPatch,
  normalizeLegacyIssueEditableCellValue,
  preserveStringArrayReferenceWhenEqual,
  resolveLegacyIssueAutoSelectedRevisionId,
  resolveLegacyIssueLocalizedDefinition,
  resolveLegacyIssueMainTab,
  resolveLegacyIssueSelectedRecordForRecords,
  shouldConfirmLegacyIssueRevisionAssigneeChange,
  sortedPublishedLegacyIssueRevisions,
  LegacyIssueRevisionOverview,
} from './CoreBusinessLegacyIssueDatasetView';

describe('legacy issue module tabs', () => {
  it('supports meeting-minutes deep links only for module views', () => {
    expect(
      resolveLegacyIssueMainTab({
        isAggregateView: false,
        tab: 'minutes',
      }),
    ).toBe('minutes');
    expect(
      resolveLegacyIssueMainTab({
        isAggregateView: true,
        tab: 'minutes',
      }),
    ).toBe('sheet');
    expect(
      resolveLegacyIssueMainTab({
        isAggregateView: false,
        tab: 'unsupported',
      }),
    ).toBe('sheet');
  });

  it('writes minutes to the tab query while preserving unrelated params', () => {
    const minutes = legacyIssueMainTabSearchParams(
      new URLSearchParams('revision_id=revision-1'),
      'minutes',
    );
    expect(minutes.toString()).toBe('revision_id=revision-1&tab=minutes');

    const sheet = legacyIssueMainTabSearchParams(minutes, 'sheet');
    expect(sheet.toString()).toBe('revision_id=revision-1');
  });
});

describe('legacy issue reflected revision defaults', () => {
  it('prepopulates new draft rows with the next revision as an editable number', () => {
    expect(
      buildLegacyIssueBlankRowDefaultValues({
        currentRevisionNo: null,
        isDraftRevision: true,
        latestPublishedRevisionNo: 3,
      }),
    ).toEqual({ introduced_revision_no: '4' });
  });

  it('uses the selected published revision for direct-edit context', () => {
    expect(
      buildLegacyIssueBlankRowDefaultValues({
        currentRevisionNo: 3,
        isDraftRevision: false,
        latestPublishedRevisionNo: 3,
      }),
    ).toEqual({ introduced_revision_no: '3' });
  });

  it('accepts a legacy Rev. prefix when saving an inline edit', () => {
    expect(
      normalizeLegacyIssueEditableCellValue('introduced_revision_no', 'Rev. 9'),
    ).toBe('9');
    expect(
      normalizeLegacyIssueEditableCellValue('introduced_revision_no', ''),
    ).toBeNull();
  });
});

function record({
  id,
  revisionId,
  stableRecordId,
  value = id,
}: {
  id: string;
  revisionId: string;
  stableRecordId: string | null;
  value?: string;
}): LegacyIssueDatasetRecord {
  return {
    attachments: [],
    created_at: '2026-06-29T00:00:00Z',
    id,
    imported_at: null,
    imported_source_filename: null,
    module_key: null,
    primary_attachment: null,
    raw_fields: {},
    revision_id: revisionId,
    stable_record_id: stableRecordId,
    updated_at: '2026-06-29T00:00:00Z',
    values: { problem: value },
  };
}

function revision({
  approvedAt = null,
  approvalRequestedAt = null,
  approverId = null,
  id,
  reviewRequestedAt = null,
  reviewedAt = null,
  reviewerId = null,
  revisionNo,
  status = 'published',
}: {
  approvedAt?: string | null;
  approvalRequestedAt?: string | null;
  approverId?: string | null;
  id: string;
  reviewRequestedAt?: string | null;
  reviewedAt?: string | null;
  reviewerId?: string | null;
  revisionNo: number | null;
  status?: LegacyIssueRevision['status'];
}): LegacyIssueRevision {
  return {
    approval_requested_at: approvalRequestedAt,
    approval_requested_by_id: null,
    approval_requested_by_name: null,
    approved_at: approvedAt,
    approved_by_id: null,
    approved_by_name: null,
    approver_email: null,
    approver_id: approverId,
    approver_name: null,
    base_revision_id: null,
    canceled_at: null,
    canceled_by_id: null,
    canceled_by_name: null,
    created_at: '2026-07-06T00:00:00Z',
    created_by_id: null,
    created_by_name: null,
    dataset_key: 'legacy_issue.common-master',
    id,
    locked_by_id: null,
    locked_by_name: null,
    note: null,
    published_at: '2026-07-06T00:00:00Z',
    published_by_id: null,
    published_by_name: null,
    review_requested_at: reviewRequestedAt,
    review_requested_by_id: null,
    review_requested_by_name: null,
    reviewed_at: reviewedAt,
    reviewed_by_id: null,
    reviewed_by_name: null,
    reviewer_email: null,
    reviewer_id: reviewerId,
    reviewer_name: null,
    revision_no: revisionNo,
    status,
    updated_at: '2026-07-06T00:00:00Z',
  };
}

function overviewHistory({
  deletedAt = null,
  id,
  linkedRevisionId = null,
  revisionNo,
  sortOrder,
}: {
  deletedAt?: string | null;
  id: string;
  linkedRevisionId?: string | null;
  revisionNo: number | null;
  sortOrder: number;
}): LegacyIssueRevisionOverviewHistory {
  return {
    approver_name: null,
    approver_user_id: null,
    author_name: null,
    author_user_id: null,
    dataset_key: 'legacy_issue.common-master.aircon',
    deleted_at: deletedAt,
    deleted_by_id: null,
    id,
    linked_revision_id: linkedRevisionId,
    origin: 'imported',
    revised_on: null,
    reviewer_name: null,
    reviewer_user_id: null,
    revision_label: revisionNo === null ? '-' : String(revisionNo),
    revision_no: revisionNo,
    sort_order: sortOrder,
    source_filename: '표지_에어컨.xlsx',
    source_row: sortOrder + 1,
    source_sha256: 'a'.repeat(64),
    source_sheet: '샤시(ACON)',
    summary: null,
    vehicle_models: null,
  };
}

describe('resolveLegacyIssueSelectedRecordForRecords', () => {
  it('keeps the exact selected record when it still exists in the loaded revision', () => {
    const selected = record({
      id: 'draft-row-1',
      revisionId: 'draft',
      stableRecordId: 'stable-1',
    });

    expect(
      resolveLegacyIssueSelectedRecordForRecords([selected], selected),
    ).toBe(selected);
  });

  it('remaps an open published record to the draft row with the same stable id', () => {
    const published = record({
      id: 'published-row-1',
      revisionId: 'published',
      stableRecordId: 'stable-1',
    });
    const draft = record({
      id: 'draft-row-1',
      revisionId: 'draft',
      stableRecordId: 'stable-1',
    });

    expect(resolveLegacyIssueSelectedRecordForRecords([draft], published)).toBe(
      draft,
    );
  });

  it('closes the selected record when the logical row is missing from the loaded revision', () => {
    const selected = record({
      id: 'published-row-1',
      revisionId: 'published',
      stableRecordId: 'stable-1',
    });
    const unrelated = record({
      id: 'draft-row-2',
      revisionId: 'draft',
      stableRecordId: 'stable-2',
    });

    expect(
      resolveLegacyIssueSelectedRecordForRecords([unrelated], selected),
    ).toBeNull();
  });
});

describe('preserveStringArrayReferenceWhenEqual', () => {
  it('keeps the previous array reference for identical column order responses', () => {
    const current = ['region_zone', 'symptom'];
    const next = ['region_zone', 'symptom'];

    expect(preserveStringArrayReferenceWhenEqual(current, next)).toBe(current);
  });

  it('returns the next array when the order changed', () => {
    const current = ['region_zone', 'symptom'];
    const next = ['symptom', 'region_zone'];

    expect(preserveStringArrayReferenceWhenEqual(current, next)).toBe(next);
  });
});

describe('legacy issue pending draft payload helpers', () => {
  it('merges local record values and removes blank values', () => {
    expect(
      mergeLegacyIssueRecordValues(
        { cause: 'old', symptom: 'noise' },
        { cause: '  new  ', symptom: '', vehicle_model: null },
      ),
    ).toEqual({ cause: 'new' });
  });

  it('preserves multi select and reference values in local record values', () => {
    expect(
      mergeLegacyIssueRecordValues(
        {},
        {
          departments: [
            {
              kind: 'orgUnit',
              id: 'org-1',
              label: 'Research',
              path: 'Headquarters / Research',
            },
          ],
          owners: [
            {
              kind: 'user',
              id: 'user-1',
              label: 'Ada Lovelace',
              email: 'ada@example.com',
            },
          ],
          regions: ['Korea', 'Europe'],
        },
      ),
    ).toEqual({
      departments: [
        {
          kind: 'orgUnit',
          id: 'org-1',
          label: 'Research',
          path: 'Headquarters / Research',
        },
      ],
      owners: [
        {
          kind: 'user',
          id: 'user-1',
          label: 'Ada Lovelace',
          email: 'ada@example.com',
        },
      ],
      regions: ['Korea', 'Europe'],
    });
  });

  it('drops pending updates when a value returns to the loaded base value', () => {
    const changed = mergePendingRecordEditPatch({
      baseValues: { symptom: 'old' },
      currentPatch: {},
      patch: { symptom: 'new' },
    });

    expect(changed).toEqual({ symptom: 'new' });
    expect(
      mergePendingRecordEditPatch({
        baseValues: { symptom: 'old' },
        currentPatch: changed,
        patch: { symptom: 'old' },
      }),
    ).toEqual({});
  });

  it('drops pending reference updates when the reference returns to the loaded base value', () => {
    const owner = {
      kind: 'user' as const,
      id: 'user-1',
      label: 'Ada Lovelace',
      email: 'ada@example.com',
    };
    const changed = mergePendingRecordEditPatch({
      baseValues: { owner },
      currentPatch: {},
      patch: {
        owner: {
          kind: 'user',
          id: 'user-2',
          label: 'Grace Hopper',
          email: 'grace@example.com',
        },
      },
    });

    expect(changed).toEqual({
      owner: {
        kind: 'user',
        id: 'user-2',
        label: 'Grace Hopper',
        email: 'grace@example.com',
      },
    });
    expect(
      mergePendingRecordEditPatch({
        baseValues: { owner },
        currentPatch: changed,
        patch: { owner },
      }),
    ).toEqual({});
  });

  it('builds a batch payload with row-level updates and pending creates', () => {
    const pendingCreate = record({
      id: 'pending-legacy-issue-create-1',
      revisionId: 'draft',
      stableRecordId: 'pending-legacy-issue-create-1',
      value: 'created',
    });
    const pendingRecordEdits = {
      'record-1': {
        cause: 'new cause',
        symptom: 'new symptom',
      },
    };
    const payload = buildLegacyIssueDraftBatchPayload({
      pendingCreateRecords: [pendingCreate],
      pendingRecordEdits,
    });

    expect(payload.updates).toEqual([
      {
        record_id: 'record-1',
        values: {
          cause: 'new cause',
          symptom: 'new symptom',
        },
      },
    ]);
    expect(payload.creates).toEqual([
      {
        client_row_id: 'pending-legacy-issue-create-1',
        values: { problem: 'created' },
      },
    ]);
    expect(
      countLegacyIssuePendingDraftChanges({
        pendingAttachmentEditsByRecordId: {
          'record-1': {
            deletedAttachmentIds: ['attachment-1'],
            descriptions: { 'attachment-2': 'updated evidence' },
            primaryAttachmentId: 'attachment-2',
          },
        },
        pendingAttachmentDraftsByRecordId: {
          'pending-legacy-issue-create-1': [
            {
              description: '',
              error: null,
              file: new File(['evidence'], 'evidence.pdf'),
              id: 'pending-attachment-1',
              status: 'pending',
            },
          ],
        },
        pendingCreateRecords: [pendingCreate],
        pendingRecordEdits,
      }),
    ).toBe(7);
    expect(
      countPendingAttachmentEdits({
        'record-1': {
          deletedAttachmentIds: ['attachment-1'],
          descriptions: { 'attachment-2': 'updated evidence' },
          primaryAttachmentId: 'attachment-2',
        },
      }),
    ).toBe(3);
  });

  it('maps batch-created records back to pending row ids', () => {
    const created = record({
      id: 'record-created-1',
      revisionId: 'draft',
      stableRecordId: 'record-created-1',
      value: 'created',
    });

    const mapped = mapLegacyIssueCreatedRecordsByClientId([
      {
        client_row_id: 'pending-legacy-issue-create-1',
        record: created,
      },
    ]);

    expect(mapped.get('pending-legacy-issue-create-1')).toBe(created);
  });

  it('reapplies pending changes over freshly loaded server records', () => {
    const loaded = record({
      id: 'record-1',
      revisionId: 'draft',
      stableRecordId: 'stable-1',
      value: 'server',
    });
    const pendingCreate = record({
      id: 'pending-legacy-issue-create-1',
      revisionId: 'draft',
      stableRecordId: 'pending-legacy-issue-create-1',
      value: 'created',
    });

    const merged = applyPendingDraftChangesToLoadedRecords({
      records: [loaded],
      pendingCreateRecords: [pendingCreate],
      pendingRecordEdits: {
        'record-1': { problem: 'local' },
      },
    });

    expect(merged.map((item) => item.id)).toEqual([
      'pending-legacy-issue-create-1',
      'record-1',
    ]);
    expect(merged[1]?.values.problem).toBe('local');
  });
});

describe('buildLegacyIssueDraftChangedCellKeys', () => {
  it('maps persisted base-to-draft changes onto current record ids', () => {
    const base = revision({ id: 'base-3', revisionNo: 3 });
    const draft = {
      ...revision({ id: 'draft-4', revisionNo: null, status: 'draft' }),
      base_revision_id: base.id,
    };

    expect(
      buildLegacyIssueDraftChangedCellKeys({
        compareResult: {
          left_revision: base,
          right_revision: draft,
          rows: [
            {
              cells: [
                {
                  changed: true,
                  field_key: 'problem',
                  field_label: '문제',
                  left_value: 'before',
                  right_value: 'after',
                },
                {
                  changed: false,
                  field_key: 'cause',
                  field_label: '원인',
                  left_value: 'same',
                  right_value: 'same',
                },
              ],
              label: 'LI-1',
              stable_record_id: 'stable-1',
              status: 'modified',
            },
            {
              cells: [
                {
                  changed: true,
                  field_key: 'problem',
                  field_label: '문제',
                  left_value: 'deleted',
                  right_value: null,
                },
              ],
              label: 'LI-2',
              stable_record_id: 'stable-removed',
              status: 'removed',
            },
          ],
        },
        records: [
          record({
            id: 'draft-record-1',
            revisionId: draft.id,
            stableRecordId: 'stable-1',
          }),
        ],
      }),
    ).toEqual(['draft-record-1:problem']);
  });
});

describe('canEditLegacyIssueAttachmentsInRevision', () => {
  it('allows a platform admin to manage attachments on the latest published revision', () => {
    expect(
      canEditLegacyIssueAttachmentsInRevision({
        canDirectEditPublishedRevision: true,
        canEditCurrentDraftRevision: false,
      }),
    ).toBe(true);
  });

  it('allows attachment changes while editing an owned draft revision', () => {
    expect(
      canEditLegacyIssueAttachmentsInRevision({
        canDirectEditPublishedRevision: false,
        canEditCurrentDraftRevision: true,
      }),
    ).toBe(true);
  });

  it('blocks attachment changes for normal members on published revisions', () => {
    expect(
      canEditLegacyIssueAttachmentsInRevision({
        canDirectEditPublishedRevision: false,
        canEditCurrentDraftRevision: false,
      }),
    ).toBe(false);
  });

  it('blocks attachment changes when neither revision edit path is available', () => {
    expect(
      canEditLegacyIssueAttachmentsInRevision({
        canDirectEditPublishedRevision: false,
        canEditCurrentDraftRevision: false,
      }),
    ).toBe(false);
  });
});

describe('canApplyLegacyIssueInlineCellEdits', () => {
  it('allows platform-admin edits on the latest published revision', () => {
    expect(
      canApplyLegacyIssueInlineCellEdits({
        canDirectEditPublishedRevision: true,
        canEditCurrentDraftRevision: false,
      }),
    ).toBe(true);
  });
});

describe('canEditLegacyIssueDraftRevision', () => {
  it('allows the draft owner to edit', () => {
    expect(
      canEditLegacyIssueDraftRevision({
        currentUserId: 'user-1',
        revision: {
          locked_by_id: 'user-1',
          status: 'draft',
        },
      }),
    ).toBe(true);
  });

  it('blocks other users from editing the draft', () => {
    expect(
      canEditLegacyIssueDraftRevision({
        currentUserId: 'user-2',
        revision: {
          locked_by_id: 'user-1',
          status: 'draft',
        },
      }),
    ).toBe(false);
  });

  it('keeps an unlocked draft read-only until it is claimed', () => {
    expect(
      canEditLegacyIssueDraftRevision({
        currentUserId: 'user-1',
        revision: {
          locked_by_id: null,
          status: 'draft',
        },
      }),
    ).toBe(false);
  });

  it('does not treat a published revision as editable draft content', () => {
    expect(
      canEditLegacyIssueDraftRevision({
        currentUserId: 'user-1',
        revision: {
          locked_by_id: null,
          status: 'published',
        },
      }),
    ).toBe(false);
  });
});

describe('canForceCancelLegacyIssueDraftRevision', () => {
  const otherUsersDraft = {
    id: 'draft-1',
    locked_by_id: 'user-1',
    status: 'draft',
  };

  it('allows a server-authorized module editor to cancel another users active draft', () => {
    expect(
      canForceCancelLegacyIssueDraftRevision({
        activeDraftId: otherUsersDraft.id,
        canForceCancelActiveDraft: true,
        currentUserId: 'admin-1',
        revision: otherUsersDraft,
      }),
    ).toBe(true);
  });

  it('does not grant force cancellation to normal users or the current editor', () => {
    expect(
      canForceCancelLegacyIssueDraftRevision({
        activeDraftId: otherUsersDraft.id,
        canForceCancelActiveDraft: false,
        currentUserId: 'user-2',
        revision: otherUsersDraft,
      }),
    ).toBe(false);
    expect(
      canForceCancelLegacyIssueDraftRevision({
        activeDraftId: otherUsersDraft.id,
        canForceCancelActiveDraft: true,
        currentUserId: 'user-1',
        revision: otherUsersDraft,
      }),
    ).toBe(false);
  });

  it('does not treat unlocked or published revisions as another users active work', () => {
    expect(
      canForceCancelLegacyIssueDraftRevision({
        activeDraftId: 'draft-unlocked',
        canForceCancelActiveDraft: true,
        currentUserId: 'admin-1',
        revision: {
          id: 'draft-unlocked',
          locked_by_id: null,
          status: 'draft',
        },
      }),
    ).toBe(false);
    expect(
      canForceCancelLegacyIssueDraftRevision({
        activeDraftId: 'published-1',
        canForceCancelActiveDraft: true,
        currentUserId: 'admin-1',
        revision: {
          id: 'published-1',
          locked_by_id: 'user-1',
          status: 'published',
        },
      }),
    ).toBe(false);
  });

  it('rejects a stale capability applied to a non-active draft', () => {
    expect(
      canForceCancelLegacyIssueDraftRevision({
        activeDraftId: 'draft-2',
        canForceCancelActiveDraft: true,
        currentUserId: 'admin-1',
        revision: otherUsersDraft,
      }),
    ).toBe(false);
  });
});

describe('canDirectEditLegacyIssuePublishedRevision', () => {
  const published = { id: 'published-1', status: 'published' as const };

  it('allows a server-authorized user to edit the latest module publication in place', () => {
    expect(
      canDirectEditLegacyIssuePublishedRevision({
        activeDraft: null,
        canDirectEditPublishedRevision: true,
        currentRevision: published,
        isAggregateView: false,
        latestPublishedRevision: published,
      }),
    ).toBe(true);
  });

  it('keeps the aggregate view read-only for platform admins', () => {
    expect(
      canDirectEditLegacyIssuePublishedRevision({
        activeDraft: null,
        canDirectEditPublishedRevision: true,
        currentRevision: published,
        isAggregateView: true,
        latestPublishedRevision: published,
      }),
    ).toBe(false);
  });

  it('blocks direct edits while a module draft exists', () => {
    expect(
      canDirectEditLegacyIssuePublishedRevision({
        activeDraft: { id: 'draft-1' },
        canDirectEditPublishedRevision: true,
        currentRevision: published,
        isAggregateView: false,
        latestPublishedRevision: published,
      }),
    ).toBe(false);
  });
});

describe('legacy issue revision overview helpers', () => {
  it('requires assigned and completed review and approval before publishing', () => {
    expect(
      isLegacyIssueRevisionReadyToPublish(
        revision({
          approvedAt: '2026-07-06T02:00:00Z',
          approverId: 'approver',
          id: 'draft',
          reviewedAt: '2026-07-06T01:00:00Z',
          reviewerId: 'reviewer',
          revisionNo: null,
          status: 'draft',
        }),
      ),
    ).toBe(true);

    expect(
      isLegacyIssueRevisionReadyToPublish(
        revision({
          approverId: 'approver',
          id: 'draft',
          reviewedAt: '2026-07-06T01:00:00Z',
          reviewerId: 'reviewer',
          revisionNo: null,
          status: 'draft',
        }),
      ),
    ).toBe(false);
  });

  it('locks completed reviewer and approver assignments', () => {
    const draft = revision({
      approvedAt: '2026-07-06T02:00:00Z',
      approverId: 'approver',
      id: 'draft',
      reviewedAt: '2026-07-06T01:00:00Z',
      reviewerId: 'reviewer',
      revisionNo: null,
      status: 'draft',
    });

    expect(
      canEditLegacyIssueRevisionAssignee({ revision: draft, role: 'reviewer' }),
    ).toBe(false);
    expect(
      canEditLegacyIssueRevisionAssignee({ revision: draft, role: 'approver' }),
    ).toBe(false);
    expect(
      isLegacyIssueRevisionAssigneeChangeBlocked({
        approverId: 'next-approver',
        reviewerId: 'reviewer',
        revision: draft,
      }),
    ).toBe(true);
  });

  it('requires confirmation when changing requested but incomplete assignees', () => {
    const draft = revision({
      approvalRequestedAt: '2026-07-06T00:20:00Z',
      approverId: 'approver',
      id: 'draft',
      reviewRequestedAt: '2026-07-06T00:10:00Z',
      reviewerId: 'reviewer',
      revisionNo: null,
      status: 'draft',
    });

    expect(
      shouldConfirmLegacyIssueRevisionAssigneeChange({
        approverId: 'approver',
        reviewerId: 'next-reviewer',
        revision: draft,
      }),
    ).toBe(true);
    expect(
      shouldConfirmLegacyIssueRevisionAssigneeChange({
        approverId: 'approver',
        reviewerId: 'reviewer',
        revision: draft,
      }),
    ).toBe(false);
  });

  it('sorts published revisions by revision number descending and hides canceled revisions', () => {
    const revisions = [
      revision({ id: 'rev-2', revisionNo: 2 }),
      revision({ id: 'draft', revisionNo: null, status: 'draft' }),
      revision({ id: 'rev-1', revisionNo: 1 }),
      revision({ id: 'canceled', revisionNo: null, status: 'canceled' }),
      revision({ id: 'rev-3', revisionNo: 3 }),
    ];

    expect(
      sortedPublishedLegacyIssueRevisions(revisions).map((item) => item.id),
    ).toEqual(['rev-3', 'rev-2', 'rev-1']);
  });

  it('merges source overview history with matching real revisions without fabricating snapshots', () => {
    const rows = buildLegacyIssueRevisionOverviewRows(
      [
        revision({ id: 'rev-20', revisionNo: 20 }),
        revision({ id: 'rev-21', revisionNo: 21 }),
      ],
      [
        overviewHistory({ id: 'source-20', revisionNo: 20, sortOrder: 0 }),
        overviewHistory({ id: 'source-19', revisionNo: 19, sortOrder: 1 }),
        overviewHistory({
          id: 'source-initial',
          revisionNo: null,
          sortOrder: 2,
        }),
      ],
    );

    expect(
      rows.map((row) => [
        row.sourceHistory?.revision_no ?? null,
        row.revision?.id ?? null,
      ]),
    ).toEqual([
      [null, 'rev-21'],
      [20, 'rev-20'],
      [19, null],
      [null, null],
    ]);
  });

  it('keeps a renamed overview row linked to its immutable published revision', () => {
    const rows = buildLegacyIssueRevisionOverviewRows(
      [revision({ id: 'rev-20', revisionNo: 20 })],
      [
        overviewHistory({
          id: 'source-20',
          linkedRevisionId: 'rev-20',
          revisionNo: 200,
          sortOrder: 0,
        }),
      ],
    );

    expect(rows).toHaveLength(1);
    expect(rows[0]?.revision?.id).toBe('rev-20');
    expect(rows[0]?.sourceHistory?.revision_no).toBe(200);
  });

  it('keeps linked overlays and actual-only revisions in descending display order', () => {
    const rows = buildLegacyIssueRevisionOverviewRows(
      [
        revision({ id: 'rev-1', revisionNo: 1 }),
        revision({ id: 'rev-2', revisionNo: 2 }),
      ],
      [
        overviewHistory({
          id: 'source-2',
          linkedRevisionId: 'rev-2',
          revisionNo: 2,
          sortOrder: 0,
        }),
      ],
    );

    expect(rows.map((row) => row.revision?.id)).toEqual(['rev-2', 'rev-1']);
  });

  it('hides a deleted overview row without deleting or re-adding its published revision', () => {
    const rows = buildLegacyIssueRevisionOverviewRows(
      [
        revision({ id: 'rev-20', revisionNo: 20 }),
        revision({ id: 'rev-21', revisionNo: 21 }),
      ],
      [
        overviewHistory({
          deletedAt: '2026-07-14T00:00:00Z',
          id: 'source-20',
          linkedRevisionId: 'rev-20',
          revisionNo: 20,
          sortOrder: 0,
        }),
      ],
    );

    expect(rows.map((row) => row.revision?.id)).toEqual(['rev-21']);
  });

  it('does not let a deleted unlinked manual row hide a future published revision', () => {
    const rows = buildLegacyIssueRevisionOverviewRows(
      [
        revision({ id: 'rev-36', revisionNo: 36 }),
        revision({ id: 'rev-37', revisionNo: 37 }),
      ],
      [
        overviewHistory({
          deletedAt: '2026-07-14T00:00:00Z',
          id: 'manual-37',
          revisionNo: 37,
          sortOrder: 0,
        }),
      ],
    );

    expect(rows.map((row) => row.revision?.id)).toEqual(['rev-37', 'rev-36']);
  });

  it('accepts only blank or nonnegative 32-bit integer overview revision numbers', () => {
    const draft = {
      approver_name: null,
      approver_user_id: null,
      author_name: null,
      author_user_id: null,
      revised_on: null,
      reviewer_name: null,
      reviewer_user_id: null,
      revision_no: null,
      summary: null,
      vehicle_models: null,
    };

    expect(isValidOverviewHistoryDraft(draft)).toBe(true);
    expect(isValidOverviewHistoryDraft({ ...draft, revision_no: 36 })).toBe(
      true,
    );
    expect(isValidOverviewHistoryDraft({ ...draft, revision_no: -1 })).toBe(
      false,
    );
    expect(isValidOverviewHistoryDraft({ ...draft, revision_no: 1.5 })).toBe(
      false,
    );
    expect(
      isValidOverviewHistoryDraft({
        ...draft,
        revision_no: 2_147_483_648,
      }),
    ).toBe(false);
  });
});

describe('resolveLegacyIssueAutoSelectedRevisionId', () => {
  it('opens an active draft when no revision was selected yet', () => {
    expect(
      resolveLegacyIssueAutoSelectedRevisionId({
        activeDraftId: 'draft-revision',
        autoSelectionAttempted: false,
        selectedRevisionId: null,
      }),
    ).toBe('draft-revision');
  });

  it('keeps an explicit revision selection over the active draft', () => {
    expect(
      resolveLegacyIssueAutoSelectedRevisionId({
        activeDraftId: 'draft-revision',
        autoSelectionAttempted: false,
        selectedRevisionId: 'published-revision',
      }),
    ).toBe('published-revision');
  });

  it('keeps the latest published default when there is no active draft', () => {
    expect(
      resolveLegacyIssueAutoSelectedRevisionId({
        activeDraftId: null,
        autoSelectionAttempted: false,
        selectedRevisionId: null,
      }),
    ).toBeNull();
  });

  it('does not auto-open a draft after the initial auto selection attempt', () => {
    expect(
      resolveLegacyIssueAutoSelectedRevisionId({
        activeDraftId: 'draft-revision',
        autoSelectionAttempted: true,
        selectedRevisionId: null,
      }),
    ).toBeNull();
  });
});

describe('resolveLegacyIssueLocalizedDefinition', () => {
  const definition: LegacyIssueDatasetDefinition = {
    fields: [],
    group_labels_en: {},
    group_labels_ko: {},
    header_rows: 2,
    hierarchy_en: ['All'],
    hierarchy_ko: ['전체'],
    key: 'common-master',
    title_en: 'Past Vehicle Issue All',
    title_ko: '과거차 전체',
  };

  it('uses shell nav translations for module view titles', () => {
    const keys: string[] = [];
    const localized = resolveLegacyIssueLocalizedDefinition({
      definition,
      isKorean: true,
      translate: (key, options) => {
        keys.push(`${options?.ns ?? 'default'}:${key}`);
        return key === 'nav.legacy-issues-cooling-module' ? '쿨링모듈' : key;
      },
      viewDefinition: LEGACY_ISSUE_VIEWS['cooling-module'],
      viewKey: 'cooling-module',
    });

    expect(keys).toEqual(['shell:nav.legacy-issues-cooling-module']);
    expect(localized).toEqual({
      hierarchy: ['전체', '쿨링모듈'],
      title: '쿨링모듈',
    });
  });

  it('uses the dataset title for the default all-items view', () => {
    const localized = resolveLegacyIssueLocalizedDefinition({
      definition,
      isKorean: true,
      translate: (key) => key,
      viewDefinition: LEGACY_ISSUE_VIEWS[LEGACY_ISSUE_DEFAULT_VIEW_KEY],
      viewKey: LEGACY_ISSUE_DEFAULT_VIEW_KEY,
    });

    expect(localized).toEqual({
      hierarchy: ['전체'],
      title: '과거차 전체',
    });
  });
});

describe('legacyIssueReferenceKindForField', () => {
  function field(
    fieldType: LegacyIssueDatasetField['field_type'],
  ): Pick<LegacyIssueDatasetField, 'field_type'> {
    return { field_type: fieldType };
  }

  it('maps employee and department fields to grid reference kinds', () => {
    expect(legacyIssueReferenceKindForField(field('user'))).toBe('user');
    expect(legacyIssueReferenceKindForField(field('orgUnit'))).toBe('orgUnit');
  });

  it('does not mark normal selectable fields as references', () => {
    expect(legacyIssueReferenceKindForField(field('select'))).toBeUndefined();
    expect(legacyIssueReferenceKindForField(field('text'))).toBeUndefined();
  });
});

describe('legacy issue revision overview summary', () => {
  it('localizes known system-generated summaries without changing user-entered text', () => {
    const translate = (key: string) =>
      key === 'coreBusiness.module.overview.initialCompressorSourceImport'
        ? '컴프레서 원본 데이터 최초 적재'
        : key;

    expect(
      displayLegacyIssueRevisionSummary(
        'Initial compressor source import',
        translate,
      ),
    ).toBe('컴프레서 원본 데이터 최초 적재');
    expect(
      displayLegacyIssueRevisionSummary('사용자 입력 요약', translate),
    ).toBe('사용자 입력 요약');
  });

  it('shows the summary read-only until the row edit button is selected', () => {
    const importedRevision = revision({
      id: 'revision-1',
      revisionNo: 0,
    });
    importedRevision.note = 'Initial compressor source import';
    const createOverviewHistory = vi.fn().mockResolvedValue(false);

    render(
      createElement(LegacyIssueRevisionOverview, {
        busy: false,
        canEditOverviewHistory: true,
        currentUserId: null,
        datasetKey: 'common-master',
        onComparePair: vi.fn(),
        onOverviewHistoryCreate: createOverviewHistory,
        onOverviewHistoryDelete: vi.fn().mockResolvedValue(true),
        onOverviewHistorySave: vi.fn().mockResolvedValue(true),
        overviewHistory: [],
        revisions: [importedRevision],
        token: null,
        viewKey: 'aircon',
        workspaceSlug: 'workspace',
      }),
    );

    expect(screen.getByText('컴프레서 원본 데이터 최초 적재')).not.toBeNull();
    expect(screen.queryByRole('textbox', { name: '변경내역 요약' })).toBeNull();
    expect(
      screen.queryByRole('button', { name: '변경내역 요약 저장' }),
    ).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '수정' }));

    expect(document.activeElement).toBe(
      screen.getByRole('spinbutton', { name: '리비전 번호' }),
    );

    expect(
      (
        screen.getByRole('textbox', {
          name: '변경내역 요약',
        }) as HTMLTextAreaElement
      ).value,
    ).toBe('컴프레서 원본 데이터 최초 적재');

    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(createOverviewHistory).toHaveBeenCalledWith(
      expect.objectContaining({
        summary: 'Initial compressor source import',
      }),
      'revision-1',
    );
  });

  it('offers only revision comparison to non-admin users when a previous revision exists', () => {
    const previousRevision = revision({
      id: 'revision-previous',
      revisionNo: 0,
    });
    const currentRevision = revision({
      id: 'revision-current',
      revisionNo: 1,
    });
    const compareRevisions = vi.fn();

    render(
      createElement(LegacyIssueRevisionOverview, {
        busy: false,
        canEditOverviewHistory: false,
        currentUserId: null,
        datasetKey: 'common-master',
        onComparePair: compareRevisions,
        onOverviewHistoryCreate: vi.fn().mockResolvedValue(false),
        onOverviewHistoryDelete: vi.fn().mockResolvedValue(false),
        onOverviewHistorySave: vi.fn().mockResolvedValue(false),
        overviewHistory: [],
        revisions: [previousRevision, currentRevision],
        token: null,
        viewKey: 'aircon',
        workspaceSlug: 'workspace',
      }),
    );

    expect(screen.queryByRole('button', { name: '수정' })).toBeNull();
    expect(screen.queryByRole('button', { name: '삭제' })).toBeNull();
    const currentRevisionRow = screen
      .getByRole('button', { name: 'Rev. 1 회의록 보기' })
      .closest('tr');
    const previousRevisionRow = screen
      .getByRole('button', { name: 'Rev. 0 회의록 보기' })
      .closest('tr');
    expect(currentRevisionRow).not.toBeNull();
    expect(previousRevisionRow).not.toBeNull();
    expect(
      (
        within(previousRevisionRow as HTMLElement).getByRole('button', {
          name: '변경 비교',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    fireEvent.click(
      within(currentRevisionRow as HTMLElement).getByRole('button', {
        name: '변경 비교',
      }),
    );

    expect(compareRevisions).toHaveBeenCalledWith({
      leftRevisionId: previousRevision.id,
      rightRevisionId: currentRevision.id,
    });
  });
});
