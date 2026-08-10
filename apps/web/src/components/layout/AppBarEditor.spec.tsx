import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FileText, MessageSquare, Search } from 'lucide-react';

import type { WorkspaceAppId } from '@/src/platform/workspaces/workspace-utils';
import type { WorkspaceBootstrapAppBarCategory } from '@/src/platform/workspaces/workspaces-api';
import { AppBarEditor } from './AppBarEditor';
import type { AppBarTranslator, AppBarWorkspaceItem } from './app-bar-model';

const translate: AppBarTranslator = (key, options) => {
  const value =
    (
      {
        'common:actions.close': '닫기',
        'shell:appBarEditor.allApps': '전체 앱',
        'shell:appBarEditor.count': `즐겨찾기 ${String(options?.count ?? '')}개`,
        'shell:appBarEditor.eyebrow': '즐겨찾기',
        'shell:appBarEditor.more': '선택 가능',
        'shell:appBarEditor.moveDown': `${String(options?.title ?? '')} 아래로 이동`,
        'shell:appBarEditor.moveUp': `${String(options?.title ?? '')} 위로 이동`,
        'shell:appBarEditor.noResults': '검색 결과가 없습니다.',
        'shell:appBarEditor.pinLabel': `${String(options?.title ?? '')} 즐겨찾기에 추가`,
        'shell:appBarEditor.pinned': '즐겨찾기',
        'shell:appBarEditor.reset': '기본값',
        'shell:appBarEditor.save': '저장',
        'shell:appBarEditor.saving': '저장 중',
        'shell:appBarEditor.searchPlaceholder': '앱 검색',
        'shell:appBarEditor.title': '즐겨찾기 편집',
        'shell:appBarEditor.uncategorized': '기타 앱',
      } as Record<string, string>
    )[key] ?? String(options?.defaultValue ?? key);
  return value;
};

const draftItems: AppBarWorkspaceItem[] = [
  { id: 'chatbot' as WorkspaceAppId, title: '챗봇', icon: MessageSquare },
  { id: 'docs' as WorkspaceAppId, title: '문서', icon: FileText },
  { id: 'web-search' as WorkspaceAppId, title: '웹 검색', icon: Search },
];

const launcherCategories: WorkspaceBootstrapAppBarCategory[] = [
  {
    id: 'ai',
    key: 'ai',
    title: 'AI',
    icon_key: 'sparkles',
    position: 0,
    items: [
      {
        app_id: 'chatbot',
        title: '챗봇',
        route_base: '/chatbot',
        icon_key: 'message-square',
        enabled: true,
      },
      {
        app_id: 'web-search',
        title: '웹 검색',
        route_base: '/web-search',
        icon_key: 'search',
        enabled: true,
      },
    ],
  },
  {
    id: 'collaboration',
    key: 'collaboration',
    title: '협업',
    icon_key: 'users',
    position: 1,
    items: [
      {
        app_id: 'docs',
        title: '문서',
        route_base: '/docs',
        icon_key: 'file-text',
        enabled: true,
      },
    ],
  },
];

function renderEditor({
  draftPinnedAppIds = ['chatbot' as WorkspaceAppId],
}: {
  draftPinnedAppIds?: WorkspaceAppId[];
} = {}) {
  const onTogglePinnedApp = vi.fn();
  render(
    <AppBarEditor
      appBarLayoutError={null}
      appBarLayoutSaving={false}
      draftItems={draftItems}
      draftPinnedAppIds={draftPinnedAppIds}
      launcherCategories={launcherCategories}
      onClose={vi.fn()}
      onMovePinnedApp={vi.fn()}
      onReset={vi.fn()}
      onSave={vi.fn()}
      onTogglePinnedApp={onTogglePinnedApp}
      pinnedEligibleAppIds={new Set(draftItems.map((item) => item.id))}
      t={translate}
    />,
  );
  return { onTogglePinnedApp };
}

describe('AppBarEditor', () => {
  it('groups available favorite apps by app bar category', () => {
    renderEditor();

    expect(screen.getByText('AI')).toBeTruthy();
    expect(screen.getByText('협업')).toBeTruthy();
    expect(
      (screen.getAllByLabelText('챗봇 즐겨찾기에 추가')[0] as HTMLInputElement)
        .checked,
    ).toBe(true);
    expect(
      (screen.getByLabelText('문서 즐겨찾기에 추가') as HTMLInputElement)
        .checked,
    ).toBe(false);
  });

  it('filters category groups with search', () => {
    renderEditor();

    fireEvent.change(screen.getByRole('searchbox', { name: '앱 검색' }), {
      target: { value: '문서' },
    });

    expect(screen.queryByText('AI')).toBeNull();
    expect(screen.getByText('협업')).toBeTruthy();
    expect(screen.getByLabelText('문서 즐겨찾기에 추가')).toBeTruthy();
  });

  it('does not disable additional apps when many favorites are already selected', () => {
    renderEditor({
      draftPinnedAppIds: [
        'chatbot',
        'whiteboard',
        'web-search',
        'pms',
        'files',
        'mail',
        'recording',
        'diagrams',
        'docs',
      ] as WorkspaceAppId[],
    });

    for (const checkbox of screen.getAllByLabelText('문서 즐겨찾기에 추가')) {
      expect((checkbox as HTMLInputElement).disabled).toBe(false);
    }
    for (const checkbox of screen.getAllByLabelText(
      '웹 검색 즐겨찾기에 추가',
    )) {
      expect((checkbox as HTMLInputElement).disabled).toBe(false);
    }
  });
});
