import type { Ref } from 'react';

import { buildDocsHtmlFrameSrcDoc } from './docs-html-frame-srcdoc';

export interface DocsHtmlFrameProps {
  title: string;
  content: string;
  enableWheelBridge?: boolean;
  iframeRef?: Ref<HTMLIFrameElement>;
  zoom?: number;
}

export function DocsHtmlFrame({
  title,
  content,
  enableWheelBridge = false,
  iframeRef,
  zoom = 1,
}: DocsHtmlFrameProps) {
  return (
    <iframe
      data-testid="docs-html-frame"
      ref={iframeRef}
      title={title}
      srcDoc={buildDocsHtmlFrameSrcDoc(content, zoom, { enableWheelBridge })}
      sandbox="allow-scripts"
      referrerPolicy="no-referrer"
      className="h-full w-full border-0 bg-white"
    />
  );
}
