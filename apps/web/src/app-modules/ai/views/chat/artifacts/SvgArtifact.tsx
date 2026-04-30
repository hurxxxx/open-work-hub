import { useMemo } from 'react';
import DOMPurify from 'dompurify';

export interface SvgArtifactProps {
  content: string;
}

// Inline SVG renderer with DOMPurify sanitation. The `svg` + `svgFilters`
// profiles allow the full animation/filter/gradient surface SVG artists
// actually use while stripping every known XSS vector: `<script>`, any
// `on*` event handler, `javascript:` URLs, and foreignObject HTML
// injection. react-markdown doesn't see SVG bodies at all — the artifact
// body IS the graphic markup.
export function SvgArtifact({ content }: SvgArtifactProps) {
  const safeHtml = useMemo(
    () =>
      DOMPurify.sanitize(content, {
        USE_PROFILES: { svg: true, svgFilters: true },
      }),
    [content],
  );
  return (
    <div
      className="artifact-svg"
      role="img"
      aria-label="SVG 아티팩트"
      // DOMPurify's output is already sanitized by the svg profile, so
      // injecting it is safe. We rely on the profile rather than a hand-
      // rolled allowlist because hand-rolled tends to miss mutation XSS.
      dangerouslySetInnerHTML={{ __html: safeHtml }}
    />
  );
}
