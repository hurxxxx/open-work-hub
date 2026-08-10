import { createElement, type ReactNode } from 'react';
import DOMPurify from 'dompurify';

const SVG_ATTRIBUTE_ALIASES: Record<string, string> = {
  class: 'className',
  'xlink:href': 'xlinkHref',
  'xml:space': 'xmlSpace',
};

export function svgReactAttributeName(name: string): string {
  const alias = SVG_ATTRIBUTE_ALIASES[name];
  if (alias) return alias;
  if (name.startsWith('aria-') || name.startsWith('data-')) return name;
  return name.replace(/-([a-z])/g, (_, char: string) => char.toUpperCase());
}

export function parseSvgStyleAttribute(styleText: string): Record<string, string> {
  return styleText.split(';').reduce<Record<string, string>>((style, declaration) => {
    const trimmed = declaration.trim();
    if (!trimmed) return style;
    const [property, ...valueParts] = trimmed.split(':');
    const name = svgReactAttributeName(property.trim());
    const value = valueParts.join(':').trim();
    if (name && value) {
      style[name] = value;
    }
    return style;
  }, {});
}

function svgElementProps(element: Element): Record<string, unknown> {
  const props: Record<string, unknown> = {};
  for (const attribute of Array.from(element.attributes)) {
    if (/^on/i.test(attribute.name)) continue;
    if (attribute.name === 'style') {
      props.style = parseSvgStyleAttribute(attribute.value);
      continue;
    }
    props[svgReactAttributeName(attribute.name)] = attribute.value;
  }
  return props;
}

function svgNodeToReact(node: ChildNode, key: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return null;
  }

  const element = node as Element;
  const children = Array.from(element.childNodes)
    .map((child, childIndex) => svgNodeToReact(child, `${key}-${childIndex}`))
    .filter((child): child is ReactNode => child !== null);

  return createElement(
    element.tagName,
    { ...svgElementProps(element), key },
    ...children,
  );
}

export function renderSanitizedSvg(content: string): ReactNode {
  if (typeof DOMParser === 'undefined') return null;
  const safeHtml = DOMPurify.sanitize(content, {
    USE_PROFILES: { svg: true, svgFilters: true },
  });
  const document = new DOMParser().parseFromString(safeHtml, 'image/svg+xml');
  const parserError = document.querySelector('parsererror');
  if (parserError || !document.documentElement) return null;
  return svgNodeToReact(document.documentElement, 'svg-root');
}
