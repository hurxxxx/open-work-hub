import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Detail, Pending } from './api';
import { translate } from './i18n';
import { Documents, Markdown, RequestForm } from './views';

vi.mock('@pierre/diffs/react', () => ({ MultiFileDiff: () => <div /> }));
const t = translate('en-US');
const task: Detail = {
  id: 'task',
  title: 'Useful change',
  stage: 'plan',
  status: 'idle',
  thread_id: 'thread',
  turn_id: null,
  root: '/repo/dev',
  isolated: false,
  approved_revision: null,
  error_code: null,
  updated_at: '2026-09-19T00:00:00Z',
  event_id: 1,
  attachments: [],
  attachment_limits: {
    file_bytes: 52428800,
    task_bytes: 524288000,
    files: 200,
    selection: 20,
  },
  items: [],
  history_truncated: false,
  requests: [],
  revisions: [
    {
      id: 1,
      kind: 'plan',
      version: 1,
      body: 'Review this plan',
      created_at: '2026-09-19T00:00:00Z',
    },
  ],
};

describe('plan authorization UI', () => {
  it('requires saving changed plan text before implementation', async () => {
    const onImplement = vi.fn();
    const onSave = vi.fn().mockResolvedValue(true);
    render(
      <Documents
        task={task}
        kind="plan"
        t={t}
        busy={false}
        onSave={onSave}
        onPlan={vi.fn()}
        onImplement={onImplement}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Edit document' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Edit document' }), {
      target: { value: 'Changed scope' },
    });
    expect(
      (
        screen.getByRole('button', {
          name: 'Implement this plan',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Save document' }));
    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        kind: 'plan',
        base_version: 1,
        body: 'Changed scope',
      }),
    );
    expect(onImplement).not.toHaveBeenCalled();
  });
  it('does not enable implementation when a newer requirements version exists', () => {
    const changed = {
      ...task,
      revisions: [
        ...task.revisions,
        {
          id: 2,
          kind: 'requirements',
          version: 1,
          body: 'New scope',
          created_at: '2026-09-19T00:01:00Z',
        },
      ],
    };
    render(
      <Documents
        task={changed}
        kind="plan"
        t={t}
        busy={false}
        onSave={vi.fn()}
        onPlan={vi.fn()}
        onImplement={vi.fn()}
      />,
    );
    expect(
      (
        screen.getByRole('button', {
          name: 'Implement this plan',
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
});

it('requires answers for all questions without auto-submitting an option', () => {
  const onAnswer = vi.fn();
  const request: Pending = {
    id: 'req',
    method: 'item/tool/requestUserInput',
    payload: {
      questions: [
        {
          id: 'scope',
          header: 'Scope',
          question: 'Which scope?',
          options: [{ label: 'Small', description: 'A focused change' }],
        },
        { id: 'check', header: 'Check', question: 'Which check?', options: [] },
      ],
    },
  };
  render(
    <RequestForm
      request={request}
      t={t}
      disabled={false}
      onAnswer={onAnswer}
    />,
  );
  expect(onAnswer).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('radio'));
  expect(
    (
      screen.getByRole('button', {
        name: 'Submit answers',
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  fireEvent.change(screen.getByLabelText('Check · Additional answer'), {
    target: { value: 'Unit tests' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Submit answers' }));
  expect(onAnswer).toHaveBeenCalledWith('req', {
    answers: { scope: ['Small'], check: ['Unit tests'] },
  });
});

it('renders untrusted markdown without active HTML or script links', () => {
  const { container } = render(
    <Markdown
      text={'<script>alert(1)</script>\n\n[click](javascript:alert(1))'}
    />,
  );
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('a')?.getAttribute('href')).not.toMatch(
    /^javascript:/,
  );
});
