function markdownFileName(title: string): string {
  const safeTitle = title.trim().replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ') || 'document';
  return `${safeTitle}.md`;
}

export function downloadMarkdownFile(title: string, markdown: string): void {
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = markdownFileName(title);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
