export interface CoreAdminSectionDefinition<TSection extends string = string> {
  id: TSection;
  path: string;
  roles: readonly string[];
}

export interface CoreAdminSectionRegistry<TSection extends string> {
  getDefaultAdminPath: (systemRoles: readonly string[]) => string;
  hasAdminSectionAccess: (
    systemRoles: readonly string[],
    section: TSection,
  ) => boolean;
  hasAnyAdminReadPermission: (systemRoles: readonly string[]) => boolean;
  sectionById: ReadonlyMap<TSection, CoreAdminSectionDefinition<TSection>>;
  sections: readonly CoreAdminSectionDefinition<TSection>[];
}

export function defineCoreAdminSections<
  const TSections extends readonly CoreAdminSectionDefinition[],
>(sections: TSections): TSections {
  return sections;
}

export function createCoreAdminSectionRegistry<
  const TSections extends readonly CoreAdminSectionDefinition[],
>(sections: TSections): CoreAdminSectionRegistry<TSections[number]['id']> {
  type SectionId = TSections[number]['id'];
  const sectionById = new Map<SectionId, CoreAdminSectionDefinition<SectionId>>(
    sections.map((section) => [
      section.id,
      {
        id: section.id,
        path: section.path,
        roles: section.roles,
      },
    ]),
  );
  const sectionRoles = new Map<SectionId, readonly string[]>(
    sections.map((section) => [section.id, section.roles]),
  );
  const readRoles = new Set<string>(
    sections.flatMap((section) => [...section.roles]),
  );

  const hasAdminSectionAccess = (
    systemRoles: readonly string[],
    section: SectionId,
  ): boolean =>
    (sectionRoles.get(section) ?? []).some((role) =>
      systemRoles.includes(role),
    );

  return {
    getDefaultAdminPath: (systemRoles) => {
      const section = sections.find((item) =>
        hasAdminSectionAccess(systemRoles, item.id),
      );
      return section ? section.path : (sections[0]?.path ?? '/admin');
    },
    hasAdminSectionAccess,
    hasAnyAdminReadPermission: (systemRoles) =>
      systemRoles.some((role) => readRoles.has(role)),
    sectionById,
    sections,
  };
}
