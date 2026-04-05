import { useEffect, useState } from 'react';

import {
  Button,
  DataTable,
  DataTableToolbar,
  DetailDrawer,
  EmptyState,
  FilterBar,
  InlineNotice,
  Panel,
  SearchField,
  type DataTableColumn,
  useToast,
} from '@aidoo/ui';

import {
  searchDocuments,
  type SearchDocumentHit,
  type SearchDocumentsFilters,
  type SearchDocumentsResponse,
} from './documents-api';

const DEFAULT_QUERY = 'compressor specification latest revision';

const VIEW_PRESETS = {
  'engineering-specs': {
    query: 'compressor specification latest revision',
    docType: 'spec',
    scope: 'engineering',
  },
  'revision-notices': {
    query: 'seal material change notice',
    docType: 'revision-note',
    scope: 'project-a',
  },
  'quality-guides': {
    query: 'supplier quality containment response',
    docType: 'guide',
    scope: 'supplier-quality',
  },
} as const;

type SavedViewId = keyof typeof VIEW_PRESETS;
type ScopeFilterId = 'engineering' | 'project-a' | 'quality' | 'supplier-quality';

const columns: DataTableColumn<SearchDocumentHit>[] = [
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
  { accessorKey: 'source_type', header: 'Type' },
  { accessorKey: 'acl', header: 'ACL' },
];

function buildFilters(docType: string, scope: ScopeFilterId): SearchDocumentsFilters {
  const filters: SearchDocumentsFilters = {
    doc_type: docType ? [docType] : [],
    project: [],
    department: [],
  };

  if (scope === 'project-a') {
    filters.project = ['Project A'];
  }
  if (scope === 'engineering') {
    filters.department = ['Engineering'];
  }
  if (scope === 'quality') {
    filters.department = ['Quality'];
  }
  if (scope === 'supplier-quality') {
    filters.department = ['Supplier Quality'];
  }

  return filters;
}

export interface SearchWorkbenchProps {
  token: string;
}

export function SearchWorkbench({ token }: SearchWorkbenchProps) {
  const [savedView, setSavedView] = useState<SavedViewId>('engineering-specs');
  const [docType, setDocType] = useState('spec');
  const [scope, setScope] = useState<ScopeFilterId>('engineering');
  const [queryInput, setQueryInput] = useState(DEFAULT_QUERY);
  const [submittedQuery, setSubmittedQuery] = useState(DEFAULT_QUERY);
  const [searchState, setSearchState] = useState<SearchDocumentsResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [selectedRow, setSelectedRow] = useState<SearchDocumentHit | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const toast = useToast();

  useEffect(() => {
    let active = true;

    async function runSearch() {
      setSearching(true);
      setSearchError(null);

      try {
        const nextState = await searchDocuments(
          {
            query: submittedQuery,
            filters: buildFilters(docType, scope),
            top_k: 8,
            answer_mode: 'search-only',
          },
          token,
        );
        if (!active) {
          return;
        }

        setSearchState(nextState);
      } catch (caughtError) {
        if (!active) {
          return;
        }
        setSearchError(
          caughtError instanceof Error
            ? caughtError.message
            : '문서 검색 결과를 불러오지 못했습니다.',
        );
      } finally {
        if (active) {
          setSearching(false);
        }
      }
    }

    void runSearch();

    return () => {
      active = false;
    };
  }, [docType, scope, submittedQuery, token]);

  useEffect(() => {
    if (!searchState?.hits.some((hit) => hit.document_id === selectedRow?.document_id)) {
      setSelectedRow(null);
      setDrawerOpen(false);
    }
  }, [searchState, selectedRow?.document_id]);

  const hits = searchState?.hits ?? [];
  const nextActions = searchState?.next_actions ?? [];

  function submitCurrentQuery() {
    setSubmittedQuery(queryInput.trim() || DEFAULT_QUERY);
  }

  function applySavedView(viewId: SavedViewId) {
    const preset = VIEW_PRESETS[viewId];
    setSavedView(viewId);
    setDocType(preset.docType);
    setScope(preset.scope);
    setQueryInput(preset.query);
    setSubmittedQuery(preset.query);
  }

  return (
    <>
      <Panel
        className="h-full"
        eyebrow="Documents"
        title="근거형 검색 작업면"
        description="문서 질의를 실제 검색 API에 보내고, 반환된 citation-ready 검색 결과를 작업면에서 바로 확인합니다."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() =>
                applySavedView('engineering-specs')
              }
            >
              기본 뷰
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setDocType('spec');
                setScope('engineering');
                setQueryInput(DEFAULT_QUERY);
                setSubmittedQuery(DEFAULT_QUERY);
                toast.info('Filters reset', '문서 검색 필터를 기본 상태로 되돌렸습니다.');
              }}
            >
              필터 초기화
            </Button>
          </>
        }
      >
        <div className="documents-workbench__saved">
          <FilterBar
            options={[
              {
                id: 'engineering-specs',
                label: 'Engineering specs',
                active: savedView === 'engineering-specs',
                onSelect: () => applySavedView('engineering-specs'),
              },
              {
                id: 'revision-notices',
                label: 'Revision notices',
                active: savedView === 'revision-notices',
                onSelect: () => applySavedView('revision-notices'),
              },
              {
                id: 'quality-guides',
                label: 'Quality guides',
                active: savedView === 'quality-guides',
                onSelect: () => applySavedView('quality-guides'),
              },
            ]}
          />
        </div>

        <div className="documents-workbench__search">
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault();
              submitCurrentQuery();
            }}
          >
            <SearchField
              aria-label="Global search"
              className="flex-1"
              onChange={(event) => setQueryInput(event.target.value)}
              shortcut="⌘K"
              value={queryInput}
            />
            <Button
              className="w-full sm:w-auto"
              size="comfortable"
              type="submit"
              variant="primary"
            >
              검색
            </Button>
          </form>
        </div>

        <div className="documents-workbench__filters">
          <FilterBar
            options={[
              {
                id: 'spec',
                label: 'Spec',
                active: docType === 'spec',
                onSelect: () => {
                  setDocType('spec');
                  submitCurrentQuery();
                },
              },
              {
                id: 'revision-note',
                label: 'Revision note',
                active: docType === 'revision-note',
                onSelect: () => {
                  setDocType('revision-note');
                  submitCurrentQuery();
                },
              },
              {
                id: 'memo',
                label: 'Memo',
                active: docType === 'memo',
                onSelect: () => {
                  setDocType('memo');
                  submitCurrentQuery();
                },
              },
              {
                id: 'guide',
                label: 'Guide',
                active: docType === 'guide',
                onSelect: () => {
                  setDocType('guide');
                  submitCurrentQuery();
                },
              },
              {
                id: 'engineering',
                label: 'Engineering',
                active: scope === 'engineering',
                onSelect: () => {
                  setScope('engineering');
                  submitCurrentQuery();
                },
              },
              {
                id: 'project-a',
                label: 'Project A',
                active: scope === 'project-a',
                onSelect: () => {
                  setScope('project-a');
                  submitCurrentQuery();
                },
              },
              {
                id: 'quality',
                label: 'Quality',
                active: scope === 'quality',
                onSelect: () => {
                  setScope('quality');
                  submitCurrentQuery();
                },
              },
              {
                id: 'supplier-quality',
                label: 'Supplier quality',
                active: scope === 'supplier-quality',
                onSelect: () => {
                  setScope('supplier-quality');
                  submitCurrentQuery();
                },
              },
            ]}
          />
        </div>

        {searchError ? (
          <div className="mb-4 rounded-[var(--ui-radius-md)] border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {searchError}
          </div>
        ) : null}

        {nextActions.length ? (
          <div className="mb-4">
            <InlineNotice title="next actions">
              {nextActions.join(' · ')}
            </InlineNotice>
          </div>
        ) : null}

        <DataTableToolbar
          title="Top results"
          meta={
            searchState
              ? `${hits.length} selected sources · ${searchState.query_profile}`
              : '검색 컨텍스트를 준비 중입니다.'
          }
        />
        <DataTable
          columns={columns}
          emptyState={
            <EmptyState
              title="검색 결과가 없습니다."
              description="질의를 구체화하거나 문서 유형과 부서 필터를 조정해보세요."
              action={{
                label: '기본 검색으로 되돌리기',
                onClick: () => applySavedView('engineering-specs'),
              }}
            />
          }
          loading={searching}
          rows={hits}
          selection={{
            selectedRowId: selectedRow?.document_id,
            getRowId: (row) => row.document_id,
            onRowClick: (row) => {
              setSelectedRow(row);
              setDrawerOpen(true);
            },
          }}
        />

        <div className="documents-workbench__footer">
          <span>
            Query profile: {searchState?.query_profile ?? 'loading'}
          </span>
          <span>
            Filters: {searchState?.filters_applied.doc_type.join(', ') || 'all'} /{' '}
            {searchState?.filters_applied.department.join(', ') ||
              searchState?.filters_applied.project.join(', ') ||
              'global'}
          </span>
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
                {selectedRow.title} · {selectedRow.page_reference}
              </div>
              <strong className="block text-base text-[var(--ui-color-ink)]">
                Selected evidence
              </strong>
              <p className="documents-detail__quote">{selectedRow.citation}</p>
            </div>

            <ul className="documents-summary-list">
              <li>
                <strong>Owner</strong>
                <span>{selectedRow.owner}</span>
              </li>
              <li>
                <strong>ACL</strong>
                <span>{selectedRow.acl} / {selectedRow.department}</span>
              </li>
              <li>
                <strong>Project</strong>
                <span>{selectedRow.project}</span>
              </li>
              <li>
                <strong>Next actions</strong>
                <span>{selectedRow.next_actions.join(' · ')}</span>
              </li>
            </ul>
          </div>
        ) : null}
      </DetailDrawer>
    </>
  );
}
