import { useMemo } from 'react';

import { renderSanitizedSvg } from './svg-artifact-renderer';

export interface SvgArtifactProps {
  content: string;
  ariaLabel: string;
}

// Inline SVG renderer with DOMPurify sanitation. The `svg` + `svgFilters`
// profiles allow the animation/filter/gradient surface SVG artists use while
// stripping XSS vectors before React renders the SVG tree.
export function SvgArtifact({ content, ariaLabel }: SvgArtifactProps) {
  const svgTree = useMemo(() => renderSanitizedSvg(content), [content]);
  return (
    <figure
      className="artifact-svg"
      aria-label={ariaLabel}
    >
      {svgTree}
    </figure>
  );
}
