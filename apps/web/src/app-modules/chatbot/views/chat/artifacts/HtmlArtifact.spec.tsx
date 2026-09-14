import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import { HtmlArtifact } from './HtmlArtifact';

it('accepts errors only from the current isolated preview and resets for a new version', () => {
  const { container, rerender } = render(
    <HtmlArtifact content="<p>saved</p>" />,
  );
  const frame = container.querySelector('iframe')!;
  const channel = JSON.parse(frame.srcdoc.match(/channel:("[^"]*")/)![1]);
  expect(frame.getAttribute('sandbox')).toBe('allow-scripts');
  expect(frame.srcdoc).toContain("connect-src 'none'");
  expect(frame.srcdoc).toContain("worker-src 'none'");
  const send = (source: Window | null, value: string) =>
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          source,
          data: { channel: value, type: 'preview-error' },
        }),
      );
    });
  send(window, channel);
  send(frame.contentWindow, 'old-version');
  expect(screen.queryByRole('status')).toBeNull();
  send(frame.contentWindow, channel);
  expect(screen.getByRole('status').textContent).toContain(
    '미리보기를 실행하지 못했습니다',
  );
  rerender(<HtmlArtifact content="<p>corrected</p>" />);
  expect(screen.queryByRole('status')).toBeNull();
});

it('keeps the source accessible when dependency compilation fails', () => {
  const { container } = render(
    <HtmlArtifact
      content="<p>saved source</p>"
      previewContent={null}
      previewError
    />,
  );
  expect(container.querySelector('iframe')).toBeNull();
  expect(screen.getByRole('status')).toBeTruthy();
  fireEvent.click(screen.getByRole('tab', { name: '소스' }));
  expect(
    screen.getByRole('tab', { name: '소스' }).getAttribute('aria-selected'),
  ).toBe('true');
  expect(screen.queryByRole('status')).toBeNull();
});
