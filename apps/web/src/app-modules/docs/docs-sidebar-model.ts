export const DOCS_SIDEBAR_SECTION_IDS = ['favorites', 'recentPages'] as const;

export type DocsSidebarSectionId = (typeof DOCS_SIDEBAR_SECTION_IDS)[number];

export function getInitialDocsSidebarExpandedSections(): DocsSidebarSectionId[] {
  return [...DOCS_SIDEBAR_SECTION_IDS];
}

export function isDocsSidebarSectionExpanded(
  expandedSections: DocsSidebarSectionId[],
  sectionId: DocsSidebarSectionId,
): boolean {
  return expandedSections.includes(sectionId);
}

export function toggleDocsSidebarSection(
  expandedSections: DocsSidebarSectionId[],
  sectionId: DocsSidebarSectionId,
): DocsSidebarSectionId[] {
  return isDocsSidebarSectionExpanded(expandedSections, sectionId)
    ? expandedSections.filter(
        (expandedSectionId) => expandedSectionId !== sectionId,
      )
    : [...expandedSections, sectionId];
}
