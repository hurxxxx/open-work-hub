import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

import { Step4Brief } from './Step4Brief';
import type { ImageGeneration } from '../../../api/image-wizard-api';

vi.mock('@/src/platform/auth/auth-provider', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));

vi.mock('../../../api/image-wizard-api', async () => {
  const actual = await vi.importActual<typeof import('../../../api/image-wizard-api')>(
    '../../../api/image-wizard-api',
  );
  return {
    ...actual,
    approveImageGeneration: vi.fn(),
    cancelImageGeneration: vi.fn(),
    downloadGeneratedImageBlob: vi.fn(),
    generateBrief: vi.fn(),
    getImageGeneration: vi.fn(),
    listImageGenerations: vi.fn(),
    setImageGenerationTemplate: vi.fn(),
  };
});

function makeGeneration(overrides: Partial<ImageGeneration> = {}): ImageGeneration {
  return {
    id: 'generation-1',
    workspace_id: 'workspace-1',
    owner_id: 'user-1',
    template_id: null,
    is_template: false,
    use_case: 'status_report',
    use_case_other: '',
    style: { chips: [], palette: 'auto', background: 'auto', quality: 'high' },
    layout: { layout_id: 'top_title_grid', aspect: '1024x1024' },
    details: { audience: '', notes: '' },
    context_refs: [],
    reference_image_keys: [],
    brief_versions: [
      {
        text: 'TITLE: Old plan\nGOAL: Old goal',
        created_at: '2026-05-03T00:00:00Z',
        edit_instruction: null,
      },
      {
        text: 'TITLE: New plan\nGOAL: New goal',
        created_at: '2026-05-03T00:01:00Z',
        edit_instruction: 'make it cleaner',
      },
    ],
    brief_status: 'ready',
    image_status: 'idle',
    image_storage_key: null,
    image_model: null,
    agent_trace_id: null,
    failure_reason: null,
    approved_at: null,
    completed_at: null,
    created_at: '2026-05-03T00:00:00Z',
    updated_at: '2026-05-03T00:01:00Z',
    ...overrides,
  };
}

describe('Step4Brief', () => {
  it('shows only the latest image plan before generation', () => {
    render(
      <Step4Brief
        workspaceSlug="hq"
        row={makeGeneration()}
        onRowReplaced={vi.fn()}
        onClone={vi.fn()}
        onDiscard={vi.fn()}
        onImageEdit={vi.fn()}
      />,
    );

    expect(screen.queryByText('Old plan')).toBeNull();
    expect(screen.queryByText('Old goal')).toBeNull();
    expect(screen.getByText('New plan')).toBeTruthy();
    expect(screen.getByText('New goal')).toBeTruthy();
    expect(screen.queryByLabelText('이미지 수정 요청')).toBeNull();
  });
});
