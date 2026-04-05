import {
  AppShell,
  Button,
  SidebarNav,
  SplitPane,
  StatusBadge,
  ToastProvider,
  ToastViewport,
  Topbar,
} from '@aidoo/ui';

import { SearchWorkbench } from '../domains/documents/search-workbench';
import { DraftPreview } from '../domains/drafts/draft-preview';
import { PlmPreview } from '../domains/plm/plm-preview';
import { WikiPmsPreview } from '../domains/wiki-pms/wiki-pms-preview';

export function App() {
  return (
    <ToastProvider>
      <AppShell
        sidebar={
          <SidebarNav
            brand={{ eyebrow: '두원공조', title: '아이두' }}
            launcher={{ label: '아이두 통합검색', hint: '⌘K' }}
            sections={[
              {
                id: 'knowledge',
                label: 'Knowledge',
                items: [
                  { id: 'documents', label: 'Documents', active: true },
                  { id: 'plm', label: 'PLM' },
                  { id: 'drafts', label: 'Drafts' },
                  { id: 'wiki-pms', label: 'Wiki / PMS' },
                  { id: 'citations', label: 'Citations' },
                ],
              },
              {
                id: 'execution',
                label: 'Execution',
                items: [
                  { id: 'jobs', label: 'Jobs' },
                  { id: 'audit-logs', label: 'Audit logs' },
                ],
              },
              {
                id: 'pinned',
                label: 'Pinned',
                items: [
                  { id: 'specs', label: 'Latest specs' },
                  { id: 'exports', label: 'Export queue' },
                  { id: 'issues', label: 'Open issues' },
                ],
              },
            ]}
            footerBadges={['Engineering', 'RBAC preview']}
          />
        }
        header={
          <Topbar
            breadcrumb="Workspace / Documents / Grounded search"
            title="아이두 AI 업무 포털"
            description="두원공조 업무 문서와 지식 자산에서 근거를 찾고, 필요한 항목은 초안 작성 흐름으로 바로 넘기는 검색 중심 작업면입니다."
            actions={
              <>
                <Button variant="secondary">Sync docs</Button>
                <Button variant="secondary">Saved views</Button>
                <Button variant="primary">New draft</Button>
                <StatusBadge>React 19 + Vite</StatusBadge>
                <StatusBadge>아이두 포털</StatusBadge>
              </>
            }
          />
        }
      >
        <SplitPane
          main={<SearchWorkbench />}
          aside={
            <>
              <PlmPreview />
              <DraftPreview />
              <WikiPmsPreview />
            </>
          }
        />
      </AppShell>
      <ToastViewport />
    </ToastProvider>
  );
}

export default App;
