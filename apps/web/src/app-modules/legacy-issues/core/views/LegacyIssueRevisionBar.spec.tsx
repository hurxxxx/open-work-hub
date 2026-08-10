import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  LegacyIssueRevisionBar,
  type LegacyIssueRevisionEventView,
  type LegacyIssueRevisionCompareView,
  type LegacyIssueRevisionView,
} from './LegacyIssueRevisionBar';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const labels: Record<string, string> = {
        'coreBusiness.grid.close': '닫기',
        'coreBusiness.revision.cancelDraft': '초안 취소',
        'coreBusiness.revision.changedFields': '변경 필드',
        'coreBusiness.revision.compare': '리비전 비교',
        'coreBusiness.revision.draft': '초안',
        'coreBusiness.revision.draftFromRevision': `초안 (기준 Rev. ${options?.revision ?? '-'})`,
        'coreBusiness.revision.finishEditing': '편집 종료',
        'coreBusiness.revision.forceCancelDraft': '초안 강제 취소',
        'coreBusiness.revision.historyInfoForceCanceled':
          '권한자 강제 취소 이력',
        'coreBusiness.revision.history': '리비전 이력',
        'coreBusiness.revision.openDraft': '초안 열기',
        'coreBusiness.revision.publish': '발행',
        'coreBusiness.revision.publishedRevision': `Rev. ${options?.revision ?? '-'}`,
        'coreBusiness.revision.restore': '복원',
        'coreBusiness.revision.saveDraft': '초안 저장',
        'coreBusiness.revision.startDraft': '수정 시작',
      };
      return labels[key] ?? key;
    },
  }),
}));

vi.mock('./LegacyIssueRevisionCompareGrid', () => ({
  LegacyIssueRevisionCompareGrid: ({
    compareResult,
    leftTitle,
    rightTitle,
  }: {
    compareResult: LegacyIssueRevisionCompareView;
    leftTitle: string;
    rightTitle: string;
  }) => (
    <div data-testid="revision-compare-grid">
      <span>{leftTitle}</span>
      <span>{rightTitle}</span>
      <span>{compareResult.rows.length}</span>
    </div>
  ),
}));

describe('LegacyIssueRevisionBar', () => {
  it('keeps revision status, selection, and actions on one scrollable row', () => {
    const published = revision({
      id: 'rev-11',
      revisionNo: 11,
      status: 'published',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={null}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={null}
        current={published}
        events={[]}
        revisions={[published]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    const toolbar = screen.getByTestId('legacy-issue-revision-toolbar');
    expect(toolbar.className).toContain('overflow-x-auto');
    const row = toolbar.firstElementChild as HTMLElement;
    expect(row.className).toContain('flex-nowrap');
    expect(row.className).not.toContain('flex-wrap');
    const revisionSelect = screen.getByRole('combobox');
    expect(row.contains(revisionSelect)).toBe(true);
    expect(revisionSelect.className).toContain('!w-36');
    expect(row.contains(screen.getByRole('button', { name: '복원' }))).toBe(
      true,
    );
  });

  it('shows open and cancel draft actions instead of start draft when an active draft exists', () => {
    const published = revision({
      id: 'rev-11',
      revisionNo: 11,
      status: 'published',
    });
    const draft = revision({
      id: 'draft-12',
      revisionNo: null,
      status: 'draft',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft
        canEditCurrentDraft={false}
        compareResult={null}
        current={published}
        events={[]}
        revisions={[draft, published]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: '초안 열기' })).not.toBeNull();
    expect(screen.getByRole('button', { name: '초안 취소' })).not.toBeNull();
    expect(screen.queryByRole('button', { name: '수정 시작' })).toBeNull();
  });

  it('hides draft mutation actions when another user is editing', () => {
    const draft = revision({
      id: 'draft-12',
      lockedById: 'other-user',
      revisionNo: null,
      status: 'draft',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={null}
        current={draft}
        events={[]}
        revisions={[draft]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: '발행' })).toBeNull();
    expect(screen.queryByRole('button', { name: '초안 취소' })).toBeNull();
    expect(screen.queryByRole('button', { name: '수정 시작' })).toBeNull();
  });

  it('lets an authorized module editor force-cancel another users current draft', () => {
    const onCancelDraft = vi.fn();
    const draft = revision({
      id: 'draft-12',
      lockedById: 'other-user',
      revisionNo: null,
      status: 'draft',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        canForceCancelActiveDraft
        compareResult={null}
        current={draft}
        events={[]}
        revisions={[draft]}
        onCancelDraft={onCancelDraft}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '초안 강제 취소' }));

    expect(onCancelDraft).toHaveBeenCalledWith(draft);
    expect(screen.queryByRole('button', { name: '초안 취소' })).toBeNull();
  });

  it('shows the force-cancel action while an authorized editor views a published revision', () => {
    const published = revision({
      id: 'rev-11',
      revisionNo: 11,
      status: 'published',
    });
    const draft = revision({
      id: 'draft-12',
      lockedById: 'other-user',
      revisionNo: null,
      status: 'draft',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        canForceCancelActiveDraft
        compareResult={null}
        current={published}
        events={[]}
        revisions={[draft, published]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: '초안 강제 취소' }),
    ).not.toBeNull();
  });

  it('offers finish editing without pending changes and save draft with changes', () => {
    const draft = revision({
      id: 'draft-12',
      revisionNo: null,
      status: 'draft',
    });

    const { rerender } = render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft
        canEditCurrentDraft
        compareResult={null}
        current={draft}
        dirtyChangeCount={0}
        events={[]}
        revisions={[draft]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSaveDraftChanges={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(
      (screen.getByRole('button', { name: '편집 종료' }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);

    rerender(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft
        canEditCurrentDraft
        compareResult={null}
        current={draft}
        dirtyChangeCount={2}
        events={[]}
        revisions={[draft]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSaveDraftChanges={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(
      (screen.getByRole('button', { name: '초안 저장' }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it('allows an unlocked draft to be claimed for editing', () => {
    const onStartDraft = vi.fn();
    const draft = revision({
      baseRevisionId: 'rev-11',
      id: 'draft-12',
      revisionNo: null,
      status: 'draft',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={null}
        current={draft}
        events={[]}
        revisions={[
          draft,
          revision({ id: 'rev-11', revisionNo: 11, status: 'published' }),
        ]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={onStartDraft}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '수정 시작' }));

    expect(onStartDraft).toHaveBeenCalledWith('rev-11');
  });

  it('shows the base revision number in the draft option', () => {
    const base = revision({
      id: 'rev-11',
      revisionNo: 11,
      status: 'published',
    });
    const draft = revision({
      baseRevisionId: base.id,
      id: 'draft-12',
      revisionNo: null,
      status: 'draft',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={draft}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={null}
        current={draft}
        events={[]}
        revisions={[draft, base]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('option', { name: '초안 (기준 Rev. 11)' }),
    ).not.toBeNull();
  });

  it('prevents revision selection while changes are pending', () => {
    const current = revision({
      id: 'rev-12',
      revisionNo: 12,
      status: 'published',
    });
    const previous = revision({
      id: 'rev-11',
      revisionNo: 11,
      status: 'published',
    });

    render(
      <LegacyIssueRevisionBar
        activeDraft={null}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={null}
        current={current}
        dirtyChangeCount={1}
        events={[]}
        revisions={[current, previous]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect((screen.getByRole('combobox') as HTMLSelectElement).disabled).toBe(
      true,
    );
  });

  it('hides canceled draft revisions from selectors and history', () => {
    const published = revision({
      id: 'rev-5',
      revisionNo: 5,
      status: 'published',
    });
    const canceledDraft = revision({
      id: 'canceled-draft-1',
      revisionNo: null,
      status: 'canceled',
    });
    const events: LegacyIssueRevisionEventView[] = [
      revisionEvent({
        action: 'cancel',
        note: 'hidden canceled event',
        revisionId: canceledDraft.id,
      }),
      revisionEvent({
        action: 'publish',
        details: { revision_no: 5 },
        note: 'shown published event',
        revisionId: published.id,
      }),
      revisionEvent({
        action: 'force_cancel',
        note: 'shown authorized-editor force cancel',
        revisionId: canceledDraft.id,
      }),
    ];

    render(
      <LegacyIssueRevisionBar
        activeDraft={null}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={null}
        current={published}
        events={events}
        revisions={[published, canceledDraft]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    expect(screen.queryByRole('option', { name: 'Rev. -' })).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '리비전 이력' }));

    expect(screen.queryByText('hidden canceled event')).toBeNull();
    expect(screen.getByText('shown published event')).not.toBeNull();
    expect(
      screen.getByText('shown authorized-editor force cancel'),
    ).not.toBeNull();
  });
  it('renders the side-by-side compare grid instead of the changed field summary table', () => {
    const left = revision({
      id: 'rev-4',
      revisionNo: 4,
      status: 'published',
    });
    const right = revision({
      id: 'rev-5',
      revisionNo: 5,
      status: 'published',
    });
    const compareResult: LegacyIssueRevisionCompareView = {
      left_revision: left,
      right_revision: right,
      rows: [
        {
          cells: [
            {
              changed: true,
              field_key: 'cause',
              field_label: '원인',
              left_value: 'old',
              right_value: 'new',
            },
          ],
          label: 'LI-001',
          stable_record_id: 'stable-1',
          status: 'modified',
        },
      ],
    };

    render(
      <LegacyIssueRevisionBar
        activeDraft={null}
        canEditActiveDraft={false}
        canEditCurrentDraft={false}
        compareResult={compareResult}
        current={right}
        events={[]}
        revisions={[right, left]}
        onCancelDraft={vi.fn()}
        onCompare={vi.fn()}
        onPublishDraft={vi.fn()}
        onRestoreRevision={vi.fn()}
        onSelectRevision={vi.fn()}
        onStartDraft={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '리비전 비교' }));

    const grid = screen.getByTestId('revision-compare-grid');
    expect(grid.textContent).toContain('Rev. 4');
    expect(grid.textContent).toContain('Rev. 5');
    expect(screen.getByRole('dialog').className).toContain('z-[130]');
    expect(screen.queryByText('변경 필드')).toBeNull();
  });
});

function revision({
  baseRevisionId = null,
  id,
  lockedById = null,
  revisionNo,
  status,
}: {
  baseRevisionId?: string | null;
  id: string;
  lockedById?: string | null;
  revisionNo: number | null;
  status: string;
}): LegacyIssueRevisionView {
  return {
    base_revision_id: baseRevisionId,
    created_at: '2026-07-02T00:00:00Z',
    id,
    locked_by_id: lockedById,
    locked_by_name: null,
    note: null,
    published_at: status === 'published' ? '2026-07-02T00:00:00Z' : null,
    published_by_name: status === 'published' ? 'User' : null,
    revision_no: revisionNo,
    status,
    updated_at: '2026-07-02T00:00:00Z',
  };
}

function revisionEvent({
  action,
  details = null,
  note,
  revisionId,
}: {
  action: string;
  details?: Record<string, unknown> | null;
  note: string;
  revisionId: string;
}): LegacyIssueRevisionEventView {
  return {
    action,
    actor_email: null,
    actor_name: 'User',
    created_at: '2026-07-02T00:00:00Z',
    details,
    id: `${revisionId}:${action}`,
    note,
    revision_id: revisionId,
  };
}
