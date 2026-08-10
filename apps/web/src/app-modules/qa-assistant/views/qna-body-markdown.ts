const BRACKETED_SECTION_MARKER = /^\[([^\]\n:]{1,24}):\s*(.+?)\]\s*$/gm;
const OCR_PAGE_MARKER = /^\[p\.(\d+)\]\s*(.*)$/gim;
const OCR_IMAGE_PLACEHOLDER = /^\s*<!--\s*image\s*-->\s*$/gim;
const EXCESSIVE_BLANK_LINES = /\n{3,}/g;

export function formatQnaBodyMarkdown(content: string): string {
  return content
    .replace(OCR_IMAGE_PLACEHOLDER, '')
    .replace(BRACKETED_SECTION_MARKER, (_match, label: string, value: string) => {
      return `\n\n### ${label.trim()}: ${value.trim()}\n`;
    })
    .replace(OCR_PAGE_MARKER, (_match, page: string, title: string) => {
      const suffix = title.trim() ? ` ${title.trim()}` : '';
      return `\n\n#### p.${page}${suffix}\n`;
    })
    .replace(EXCESSIVE_BLANK_LINES, '\n\n')
    .trim();
}
