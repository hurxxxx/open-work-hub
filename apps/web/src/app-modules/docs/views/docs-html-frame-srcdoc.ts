export function normalizeDocsHtmlZoom(zoom: number): number {
  return Number.isFinite(zoom) && zoom > 0 ? Math.round(zoom * 100) / 100 : 1;
}

function htmlZoomStyle(resolvedZoom: number): string {
  return `<style data-open-alm-html-zoom>html{zoom:${resolvedZoom.toFixed(2)};}</style>`;
}

const HTML_WHEEL_BRIDGE_SCRIPT = `<script data-open-alm-wheel-bridge>(function(){if(window.__aiDoWheelBridge)return;window.__aiDoWheelBridge=true;function canScroll(el,dx,dy){if(!el||el===document)return false;var style=window.getComputedStyle(el);var canY=Math.abs(dy)>0&&/(auto|scroll|overlay)/.test(style.overflowY)&&el.scrollHeight>el.clientHeight;var canX=Math.abs(dx)>0&&/(auto|scroll|overlay)/.test(style.overflowX)&&el.scrollWidth>el.clientWidth;var yRoom=canY&&(dy<0?el.scrollTop>0:el.scrollTop+el.clientHeight<el.scrollHeight);var xRoom=canX&&(dx<0?el.scrollLeft>0:el.scrollLeft+el.clientWidth<el.scrollWidth);return yRoom||xRoom;}function findScrollable(start,dx,dy){var node=start;while(node&&node!==document.body&&node!==document.documentElement){if(canScroll(node,dx,dy))return node;node=node.parentElement;}return document.scrollingElement||document.documentElement;}window.addEventListener('message',function(event){var data=event.data;if(!data||data.type!=='open-alm-docs-html-wheel')return;var dx=Number(data.deltaX)||0;var dy=Number(data.deltaY)||0;var x=Number(data.clientX);var y=Number(data.clientY);var start=Number.isFinite(x)&&Number.isFinite(y)?document.elementFromPoint(x,y):document.scrollingElement;var target=findScrollable(start,dx,dy);if(target&&typeof target.scrollBy==='function'){target.scrollBy({left:dx,top:dy,behavior:'auto'});}else{window.scrollBy(dx,dy);}});})();</script>`;

interface DocsHtmlFrameSrcDocOptions {
  enableWheelBridge?: boolean;
}

function docsHtmlFrameInserts(
  zoom: number,
  options: DocsHtmlFrameSrcDocOptions,
): string {
  const resolvedZoom = normalizeDocsHtmlZoom(zoom);
  return [
    resolvedZoom === 1 ? '' : htmlZoomStyle(resolvedZoom),
    options.enableWheelBridge ? HTML_WHEEL_BRIDGE_SCRIPT : '',
  ].join('');
}

export function insertDocsHtmlFrameInserts(content: string, inserts: string): string {
  if (!inserts) {
    return content;
  }

  if (/<head(\s[^>]*)?>/i.test(content)) {
    return content.replace(
      /<head(\s[^>]*)?>/i,
      (match) => `${match}${inserts}`,
    );
  }
  if (/<html(\s[^>]*)?>/i.test(content)) {
    return content.replace(
      /<html(\s[^>]*)?>/i,
      (match) => `${match}<head>${inserts}</head>`,
    );
  }
  return `${inserts}${content}`;
}

export function buildDocsHtmlFrameSrcDoc(
  content: string,
  zoom = 1,
  options: DocsHtmlFrameSrcDocOptions = {},
): string {
  return insertDocsHtmlFrameInserts(
    content,
    docsHtmlFrameInserts(zoom, options),
  );
}
