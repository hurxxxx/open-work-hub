import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HtmlArtifact } from './HtmlArtifact';

describe('HtmlArtifact', () => {
  const sample = '<!doctype html><title>Demo</title><body>hi</body>';

  it('defaults to the Preview tab with a sandboxed iframe', () => {
    const { container } = render(
      <HtmlArtifact content={sample} title="데모" />,
    );
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute('srcdoc')).toBe(sample);
    // `allow-scripts` without `allow-same-origin` — the safety model
    // that lets us execute guest JS without exposing parent cookies.
    expect(iframe?.getAttribute('sandbox')).toBe('allow-scripts');
    // The Preview tab is the one selected on mount.
    expect(
      screen.getByRole('tab', { name: '프리뷰' }).getAttribute('aria-selected'),
    ).toBe('true');
    expect(
      screen.getByRole('tab', { name: '소스' }).getAttribute('aria-selected'),
    ).toBe('false');
  });

  it('switches to the Source view when the Source tab is clicked', () => {
    const { container } = render(
      <HtmlArtifact content={sample} title="데모" />,
    );
    fireEvent.click(screen.getByRole('tab', { name: '소스' }));
    expect(container.querySelector('iframe')).toBeNull();
    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code?.className).toMatch(/language-html/);
    expect(code?.textContent).toBe(sample);
  });

  it('falls back to a generic title on the iframe when none was supplied', () => {
    const { container } = render(<HtmlArtifact content={sample} />);
    const iframe = container.querySelector('iframe');
    expect(iframe?.getAttribute('title')).toBe('HTML 아티팩트 프리뷰');
  });
});
