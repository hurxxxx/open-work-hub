import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

import type {
  HermesFile,
  HermesFileRevision,
  HermesRun,
} from '../../api/hermes-agent-api';
import {
  generatedPreviews,
  HermesGeneratedResults,
} from './HermesGeneratedResults';

const revision: HermesFileRevision = {
  id: 'revision-1',
  file_id: 'file-1',
  session_id: 'session-1',
  run_id: 'run-1',
  relative_path: 'report.html',
  media_type: 'text/html',
  size_bytes: 128,
  sha256: 'a'.repeat(64),
  created_at: '2026-09-14T01:00:00Z',
  expires_at: '2026-10-14T01:00:00Z',
};
const file: HermesFile = {
  ...revision,
  id: revision.file_id,
  updated_at: revision.created_at,
};
const run: HermesRun = {
  id: 'run-1',
  session_binding_id: 'session-1',
  status: 'completed',
  kind: 'interactive',
  progress_percent: 100,
  created_at: revision.created_at,
  updated_at: revision.created_at,
};
const props = () => ({
  sessionId: revision.session_id,
  files: [file],
  revisions: [revision],
  runs: [run],
  canAutoOpen: true,
  onOpenFile: vi.fn(),
});

beforeEach(() => {
  Object.defineProperty(document, 'visibilityState', {
    value: 'visible',
    configurable: true,
  });
});

it('shows an existing generated HTML outside execution details and opens its exact version', () => {
  const input = props();
  render(<HermesGeneratedResults {...input} />);
  expect(input.onOpenFile).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /report.html/ }));
  expect(input.onOpenFile).toHaveBeenCalledWith('file-1', 'revision-1');
});

it('does not infer ownership from filenames, uploaded revisions or a stale digest', () => {
  expect(
    generatedPreviews(
      [file],
      [{ ...revision, session_id: 'foreign' }],
      'session-1',
    ),
  ).toEqual([]);
  expect(
    generatedPreviews([file], [{ ...revision, run_id: null }], 'session-1'),
  ).toEqual([]);
  expect(
    generatedPreviews([file], [{ ...revision, sha256: 'other' }], 'session-1'),
  ).toEqual([]);
  expect(
    generatedPreviews(
      [file],
      [{ ...revision, id: 'new-upload', run_id: null }, revision],
      'session-1',
    ),
  ).toEqual([]);
});

it('auto-opens once only after an opted-in, observed run completes', () => {
  const input = props();
  const { rerender } = render(
    <HermesGeneratedResults
      {...input}
      runs={[{ ...input.runs[0], status: 'running' }]}
    />,
  );
  fireEvent.click(screen.getByRole('checkbox'));
  screen.getByRole('checkbox').focus();
  rerender(<HermesGeneratedResults {...input} />);
  expect(input.onOpenFile).toHaveBeenCalledExactlyOnceWith(
    'file-1',
    'revision-1',
  );
  rerender(<HermesGeneratedResults {...input} runs={[...input.runs]} />);
  expect(input.onOpenFile).toHaveBeenCalledTimes(1);
});

it.each(['failed', 'cancelled', 'invalid_output'] as const)(
  'never auto-opens a %s run',
  (status) => {
    const input = props();
    const { rerender } = render(
      <HermesGeneratedResults
        {...input}
        runs={[{ ...input.runs[0], status: 'running' }]}
      />,
    );
    fireEvent.click(screen.getByRole('checkbox'));
    rerender(
      <HermesGeneratedResults
        {...input}
        runs={[{ ...input.runs[0], status }]}
      />,
    );
    expect(input.onOpenFile).not.toHaveBeenCalled();
  },
);

it('does not open old results when opting in after reload', () => {
  const input = props();
  render(<HermesGeneratedResults {...input} />);
  fireEvent.click(screen.getByRole('checkbox'));
  expect(input.onOpenFile).not.toHaveBeenCalled();
});

it('opens a new run that finishes between polls without opening the initial history', () => {
  const input = props();
  const { rerender } = render(
    <HermesGeneratedResults {...input} loaded={false} runs={[]} />,
  );
  expect(screen.getByRole('checkbox').hasAttribute('disabled')).toBe(true);
  rerender(<HermesGeneratedResults {...input} runs={[]} />);
  fireEvent.click(screen.getByRole('checkbox'));
  rerender(<HermesGeneratedResults {...input} />);
  expect(input.onOpenFile).toHaveBeenCalledExactlyOnceWith(
    'file-1',
    'revision-1',
  );
});

it.each(['editing', 'panel', 'hidden'])(
  'does not interrupt %s or open the result later',
  (reason) => {
    const input = props();
    const { rerender } = render(
      <>
        <textarea aria-label="Draft" />
        <HermesGeneratedResults
          {...input}
          runs={[{ ...input.runs[0], status: 'running' }]}
        />
      </>,
    );
    fireEvent.click(screen.getByRole('checkbox'));
    if (reason === 'editing') {
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'Unfinished draft' },
      });
      screen.getByRole('textbox').focus();
    }
    if (reason === 'hidden')
      Object.defineProperty(document, 'visibilityState', {
        value: 'hidden',
        configurable: true,
      });
    rerender(
      <>
        <textarea aria-label="Draft" />
        <HermesGeneratedResults {...input} canAutoOpen={reason !== 'panel'} />
      </>,
    );
    expect(input.onOpenFile).not.toHaveBeenCalled();
    screen.getByRole('textbox').blur();
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      configurable: true,
    });
    rerender(
      <>
        <textarea aria-label="Draft" />
        <HermesGeneratedResults {...input} />
      </>,
    );
    expect(input.onOpenFile).not.toHaveBeenCalled();
  },
);
