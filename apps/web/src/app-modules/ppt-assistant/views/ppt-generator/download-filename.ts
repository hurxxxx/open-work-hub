export function buildPptDownloadFilename(
  titleSource: string,
  jobId: string | null,
): string {
  const base = (titleSource || '')
    .replace(/\[\uCCA8\uBD80 \uBB38\uC11C \uB0B4\uC6A9\][\s\S]*$/, '')
    .replace(/[\\/:*?"<>|\r\n\t]+/g, ' ')
    .trim()
    .slice(0, 24)
    .trim();
  const suffix = (jobId || '').slice(0, 6);
  const title = base || '\uB450\uC6D0\uACF5\uC870_PPT';
  return suffix ? `${title}_${suffix}` : title;
}
