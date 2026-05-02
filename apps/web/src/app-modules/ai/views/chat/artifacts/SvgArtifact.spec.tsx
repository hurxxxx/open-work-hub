import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SvgArtifact } from './SvgArtifact';

describe('SvgArtifact', () => {
  it('renders a legitimate SVG graphic inline', () => {
    const svg =
      '<svg viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="red"/></svg>';
    const { container } = render(<SvgArtifact content={svg} ariaLabel="SVG artifact" />);
    const rendered = container.querySelector('svg');
    expect(rendered).not.toBeNull();
    const circle = container.querySelector('circle');
    expect(circle?.getAttribute('r')).toBe('4');
  });

  it('strips <script> tags injected into an SVG body (XSS defense)', () => {
    const hostile =
      '<svg viewBox="0 0 10 10"><script>alert(1)</script><rect width="10" height="10"/></svg>';
    const { container } = render(<SvgArtifact content={hostile} ariaLabel="SVG artifact" />);
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('rect')).not.toBeNull();
  });

  it('strips `on*` event handler attributes (mutation XSS defense)', () => {
    const hostile =
      '<svg viewBox="0 0 10 10"><rect width="10" height="10" onload="alert(1)"/></svg>';
    const { container } = render(<SvgArtifact content={hostile} ariaLabel="SVG artifact" />);
    const rect = container.querySelector('rect');
    expect(rect).not.toBeNull();
    expect(rect?.hasAttribute('onload')).toBe(false);
  });
});
