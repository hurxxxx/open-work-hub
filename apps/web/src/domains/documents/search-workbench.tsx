import { useState } from 'react';

import {
  Button,
  DataTable,
  DataTableToolbar,
  DetailDrawer,
  FilterBar,
  InlineNotice,
  Panel,
  SearchField,
  type DataTableColumn,
  useToast,
} from '@aidoo/ui';

type SearchRow = {
  id: string;
  title: string;
  summary: string;
  updated: string;
  type: string;
  acl: string;
  citation: string;
};

const rows: SearchRow[] = [
  {
    id: 'spec-kx-21',
    title: 'KX-21 Compressor Specification',
    summary: 'Pressure rating and seal material revisions indexed',
    updated: '2026-04-02',
    type: 'SPEC',
    acl: 'engineering',
    citation:
      'Revision R12 updates the approved seal material and tightens the pressure rating requirement for high-temperature operation.',
  },
  {
    id: 'revision-seal-material',
    title: 'Seal Material Change Notice',
    summary: 'Revision note with page-level citation anchors',
    updated: '2026-03-28',
    type: 'REVISION NOTE',
    acl: 'engineering',
    citation:
      'Change notice confirms the seal material replacement and links the update to project-specific approval history.',
  },
];

const columns: DataTableColumn<SearchRow>[] = [
  {
    accessorKey: 'title',
    header: 'Document',
    cell: ({ row }) => (
      <span className="block">
        <strong className="block text-[0.94rem]">{row.original.title}</strong>
        <small className="mt-1 block text-[0.82rem] text-[var(--ui-color-ink-subtle)]">
          {row.original.summary}
        </small>
      </span>
    ),
  },
  { accessorKey: 'updated', header: 'Updated' },
  { accessorKey: 'type', header: 'Type' },
  { accessorKey: 'acl', header: 'ACL' },
];

export function SearchWorkbench() {
  const [selectedRow, setSelectedRow] = useState<SearchRow | null>(rows[0]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const toast = useToast();

  return (
    <>
      <Panel
        className="h-full"
        eyebrow="Documents"
        title="근거형 검색 작업면"
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() =>
                toast.info('Saved views', '저장된 검색 뷰 관리 기능은 다음 단계에서 연결됩니다.')
              }
            >
              저장된 뷰
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                toast.info('Filters', '필터 편집 기능은 공통 FilterBar 위에서 확장됩니다.')
              }
            >
              필터 편집
            </Button>
          </>
        }
      >
        <div className="documents-workbench__saved">
          <FilterBar
            options={[
              { id: 'specs', label: 'Engineering specs', active: true },
              { id: 'revisions', label: 'Recent revisions' },
              { id: 'history', label: 'My history' },
              { id: 'temperature', label: 'High temperature' },
            ]}
          />
        </div>

        <div className="documents-workbench__search">
          <div className="flex flex-col gap-3 sm:flex-row">
            <SearchField
              aria-label="Global search"
              className="flex-1"
              defaultValue="compressor specification latest revision"
              shortcut="⌘K"
            />
            <Button className="w-full sm:w-auto" variant="primary" size="comfortable">
              검색
            </Button>
          </div>
        </div>

        <div className="documents-workbench__filters">
          <FilterBar
            options={[
              { id: 'updated', label: 'Updated 30d', active: true },
              { id: 'spec', label: 'Spec' },
              { id: 'project', label: 'Project A' },
              { id: 'department', label: 'Engineering' },
            ]}
          />
        </div>

        <DataTableToolbar
          title="Top results"
          meta="2 selected sources · hybrid ranking"
        />
        <DataTable
          columns={columns}
          rows={rows}
          selection={{
            selectedRowId: selectedRow?.id,
            getRowId: (row) => row.id,
            onRowClick: (row) => {
              setSelectedRow(row);
              setDrawerOpen(true);
            },
          }}
        />

        <div className="documents-workbench__footer">
          <span>Query profile: bm25 + vector + rerank</span>
          <span>Grounded answer path ready</span>
        </div>
      </Panel>

      <DetailDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title={selectedRow?.title ?? 'Selected document'}
        description="선택 문서의 citation, 권한 범위, 다음 액션을 확인합니다."
        actions={
          <>
            <Button
              fullWidth
              variant="primary"
              size="comfortable"
              onClick={() =>
                toast.success(
                  'Citation added',
                  '선택 근거를 초안 작성 큐에 추가했습니다.',
                )
              }
            >
              초안에 근거 추가
            </Button>
            <Button
              fullWidth
              variant="secondary"
              size="comfortable"
              onClick={() =>
                toast.info('Open source', '원문 보기 연결은 문서 상세 라우트와 함께 붙습니다.')
              }
            >
              원문 열기
            </Button>
          </>
        }
      >
        {selectedRow ? (
          <div className="documents-detail">
            <InlineNotice title="citation required">
              문서 답변은 citation 없는 자유 생성 응답으로 처리하지 않습니다.
            </InlineNotice>

            <div className="rounded-[var(--ui-radius-md)] border border-[var(--ui-color-border)] bg-[var(--ui-color-surface)] p-4">
              <div className="mb-3 text-sm text-[var(--ui-color-ink-subtle)]">
                {selectedRow.title} · pp. 4-7
              </div>
              <strong className="block text-base text-[var(--ui-color-ink)]">
                Selected evidence
              </strong>
              <p className="documents-detail__quote">{selectedRow.citation}</p>
            </div>

            <ul className="documents-summary-list">
              <li>
                <strong>Owner</strong>
                <span>Engineering Standards Team</span>
              </li>
              <li>
                <strong>ACL</strong>
                <span>{selectedRow.acl} / design-review</span>
              </li>
              <li>
                <strong>Next action</strong>
                <span>draft-generation with citation blocks</span>
              </li>
            </ul>
          </div>
        ) : null}
      </DetailDrawer>
    </>
  );
}
