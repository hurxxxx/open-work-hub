import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type {
  AppSidebarConfig,
  AppSidebarRenderContext,
} from '@/src/app/shell/sidebar-types';
import type { NavItem } from '@/src/app/shell/navigation-types';
import {
  LEGACY_ISSUE_ASSISTANT_HISTORY_NAV_ITEM_ID,
  LEGACY_ISSUE_ASSISTANT_NAV_ITEM_ID,
  LEGACY_ISSUE_COMMON_CODE_NAV_ITEM_ID,
  LEGACY_ISSUE_DATASETS,
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID,
  LEGACY_ISSUE_FIELD_SETTINGS_NAV_ITEM_ID,
  LEGACY_ISSUE_VEHICLE_CHECKLISTS_NAV_ITEM_ID,
  LEGACY_ISSUE_VEHICLE_MANAGEMENT_NAV_ITEM_ID,
  LEGACY_ISSUE_VIEWS,
} from './core/public-api';
import { cn } from '@/src/lib/utils';
import {
  hasAdminConsoleAccess,
  hasWorkspaceAdminAccess,
} from '@/src/platform/auth/auth-api';
import { resolveNavItemHref } from '@/src/platform/workspaces/workspace-utils';

const LEGACY_ISSUES_CATEGORY = 'legacy-issues-root';
const ASSISTANT_ID = LEGACY_ISSUE_ASSISTANT_NAV_ITEM_ID;
const ASSISTANT_HISTORY_ID = LEGACY_ISSUE_ASSISTANT_HISTORY_NAV_ITEM_ID;
const FIELD_SETTINGS_ID = LEGACY_ISSUE_FIELD_SETTINGS_NAV_ITEM_ID;
const DIRECT_EDIT_PERMISSIONS_ID =
  LEGACY_ISSUE_DIRECT_EDIT_PERMISSIONS_NAV_ITEM_ID;
const COMMON_CODE_ID = LEGACY_ISSUE_COMMON_CODE_NAV_ITEM_ID;
const VEHICLE_CHECKLISTS_ID = LEGACY_ISSUE_VEHICLE_CHECKLISTS_NAV_ITEM_ID;
const VEHICLE_MANAGEMENT_ID = LEGACY_ISSUE_VEHICLE_MANAGEMENT_NAV_ITEM_ID;
const COMMON_MASTER_ID = LEGACY_ISSUE_DATASETS['common-master'].navItemId;
const AIRCON_ID = LEGACY_ISSUE_VIEWS.aircon.navItemId;
const HEAT_EXCHANGER_ID = LEGACY_ISSUE_VIEWS['heat-exchanger'].navItemId;
const COMPRESSOR_MECHANICAL_ID =
  LEGACY_ISSUE_VIEWS['compressor-mechanical'].navItemId;
const COMPRESSOR_ELECTRIC_ID =
  LEGACY_ISSUE_VIEWS['compressor-electric'].navItemId;
const INTERIOR_ID = LEGACY_ISSUE_VIEWS.interior.navItemId;
const COOLING_MODULE_ID = LEGACY_ISSUE_VIEWS['cooling-module'].navItemId;
const ELECTRICAL_MECHANICAL_ID =
  LEGACY_ISSUE_VIEWS['electrical-mechanical'].navItemId;
const ELECTRICAL_CONTROL_HW_ID =
  LEGACY_ISSUE_VIEWS['electrical-control-hw'].navItemId;
const ELECTRICAL_CONTROL_SW_ID =
  LEGACY_ISSUE_VIEWS['electrical-control-sw'].navItemId;

function navById(items: NavItem[], id: string): NavItem | null {
  return items.find((item) => item.id === id) ?? null;
}

function hasAnyNavItem(...items: Array<NavItem | null>): boolean {
  return items.some(Boolean);
}

type SidebarItemIndent = 'root' | 'child';

const SIDEBAR_ITEM_INDENT_CLASS: Record<SidebarItemIndent, string> = {
  root: 'ml-1',
  child: 'ml-5',
};

function SidebarItem({
  context,
  indent = 'root',
  item,
}: {
  context: AppSidebarRenderContext;
  indent?: SidebarItemIndent;
  item: NavItem | null;
}) {
  if (!item) return null;
  const Icon = item.icon;
  return (
    <Link
      className={cn(
        'sidebar-submenu-item',
        SIDEBAR_ITEM_INDENT_CLASS[indent],
        context.activeNavItemId === item.id && 'sidebar-submenu-item-active',
      )}
      onClick={context.onNavigate}
      to={resolveNavItemHref(item, context.currentWorkspaceSlug, context.user)}
    >
      <Icon
        size={indent === 'root' ? 16 : 14}
        className="text-app-ink/55 dark:text-app-ink/65"
      />
      <span className="sidebar-submenu-label">{item.title}</span>
    </Link>
  );
}

function SidebarSection({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <div className="space-y-1">
      <div className="sidebar-section-label px-3 py-1 text-app-ink/45">
        {label}
      </div>
      {children}
    </div>
  );
}

function LegacyIssuesSidebar(context: AppSidebarRenderContext) {
  const { t } = useTranslation('shell');
  const [electricalExpanded, setElectricalExpanded] = useState(true);
  const [compressorExpanded, setCompressorExpanded] = useState(true);
  const assistant = navById(context.filteredItems, ASSISTANT_ID);
  const assistantHistory = navById(context.filteredItems, ASSISTANT_HISTORY_ID);
  const fieldSettings = navById(context.filteredItems, FIELD_SETTINGS_ID);
  const directEditPermissions = navById(
    context.filteredItems,
    DIRECT_EDIT_PERMISSIONS_ID,
  );
  const commonCode = navById(context.filteredItems, COMMON_CODE_ID);
  const vehicleChecklists = navById(
    context.filteredItems,
    VEHICLE_CHECKLISTS_ID,
  );
  const vehicleManagement = navById(
    context.filteredItems,
    VEHICLE_MANAGEMENT_ID,
  );
  const commonMaster = navById(context.filteredItems, COMMON_MASTER_ID);
  const aircon = navById(context.filteredItems, AIRCON_ID);
  const heatExchanger = navById(context.filteredItems, HEAT_EXCHANGER_ID);
  const compressorMechanical = navById(
    context.filteredItems,
    COMPRESSOR_MECHANICAL_ID,
  );
  const compressorElectric = navById(
    context.filteredItems,
    COMPRESSOR_ELECTRIC_ID,
  );
  const interior = navById(context.filteredItems, INTERIOR_ID);
  const coolingModule = navById(context.filteredItems, COOLING_MODULE_ID);
  const electricalMechanical = navById(
    context.filteredItems,
    ELECTRICAL_MECHANICAL_ID,
  );
  const electricalControlHw = navById(
    context.filteredItems,
    ELECTRICAL_CONTROL_HW_ID,
  );
  const electricalControlSw = navById(
    context.filteredItems,
    ELECTRICAL_CONTROL_SW_ID,
  );
  const electricalNavItemIds = [
    ELECTRICAL_MECHANICAL_ID,
    ELECTRICAL_CONTROL_HW_ID,
    ELECTRICAL_CONTROL_SW_ID,
  ];
  const compressorNavItemIds = [
    COMPRESSOR_MECHANICAL_ID,
    COMPRESSOR_ELECTRIC_ID,
  ];
  const compressorActive = compressorNavItemIds.some(
    (itemId) => itemId === context.activeNavItemId,
  );
  const showCompressorChildren = compressorExpanded || compressorActive;
  const electricalActive = electricalNavItemIds.some(
    (itemId) => itemId === context.activeNavItemId,
  );
  const showElectricalChildren = electricalExpanded || electricalActive;
  const canManageFields = hasWorkspaceAdminAccess(
    context.user,
    context.currentWorkspaceSlug,
  );
  const canManageDirectEditPermissions = hasAdminConsoleAccess(context.user);
  const showElectricalSection = hasAnyNavItem(
    electricalMechanical,
    electricalControlHw,
    electricalControlSw,
  );
  const showCompressorSection = hasAnyNavItem(
    compressorMechanical,
    compressorElectric,
  );
  const showMasterSection = hasAnyNavItem(
    commonMaster,
    aircon,
    heatExchanger,
    compressorMechanical,
    compressorElectric,
    interior,
    coolingModule,
    electricalMechanical,
    electricalControlHw,
    electricalControlSw,
  );
  const showChecklistSection = hasAnyNavItem(vehicleChecklists);
  const showAnalysisSection = hasAnyNavItem(assistant, assistantHistory);
  const showSettingsSection =
    Boolean(vehicleManagement) ||
    (canManageFields && hasAnyNavItem(commonCode, fieldSettings)) ||
    (canManageDirectEditPermissions && Boolean(directEditPermissions));

  return (
    <section className="space-y-5">
      {showMasterSection ? (
        <SidebarSection label={t('categories.legacy-issues-master-data')}>
          <SidebarItem context={context} item={commonMaster} />
          <SidebarItem context={context} item={aircon} />
          <SidebarItem context={context} item={heatExchanger} />
          {showCompressorSection ? (
            <div className="space-y-1">
              <button
                className={cn(
                  'sidebar-submenu-group ml-1 w-full text-left transition-colors hover:bg-app-surface-hover',
                  compressorActive && 'sidebar-submenu-item-active',
                )}
                type="button"
                onClick={() => setCompressorExpanded((current) => !current)}
              >
                {showCompressorChildren ? (
                  <ChevronDown
                    size={14}
                    className="text-app-ink/55 dark:text-app-ink/65"
                  />
                ) : (
                  <ChevronRight
                    size={14}
                    className="text-app-ink/55 dark:text-app-ink/65"
                  />
                )}
                <span className="sidebar-submenu-label">
                  {t('categories.legacy-issues-compressor')}
                </span>
              </button>
              {showCompressorChildren ? (
                <div className="space-y-1">
                  <SidebarItem
                    context={context}
                    indent="child"
                    item={compressorMechanical}
                  />
                  <SidebarItem
                    context={context}
                    indent="child"
                    item={compressorElectric}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
          <SidebarItem context={context} item={interior} />
          <SidebarItem context={context} item={coolingModule} />
          {showElectricalSection ? (
            <div className="space-y-1">
              <button
                className={cn(
                  'sidebar-submenu-group ml-1 w-full text-left transition-colors hover:bg-app-surface-hover',
                  electricalActive && 'sidebar-submenu-item-active',
                )}
                type="button"
                onClick={() => setElectricalExpanded((current) => !current)}
              >
                {showElectricalChildren ? (
                  <ChevronDown
                    size={14}
                    className="text-app-ink/55 dark:text-app-ink/65"
                  />
                ) : (
                  <ChevronRight
                    size={14}
                    className="text-app-ink/55 dark:text-app-ink/65"
                  />
                )}
                <span className="sidebar-submenu-label">
                  {t('categories.legacy-issues-electrical')}
                </span>
              </button>
              {showElectricalChildren ? (
                <div className="space-y-1">
                  <SidebarItem
                    context={context}
                    indent="child"
                    item={electricalMechanical}
                  />
                  <SidebarItem
                    context={context}
                    indent="child"
                    item={electricalControlHw}
                  />
                  <SidebarItem
                    context={context}
                    indent="child"
                    item={electricalControlSw}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
        </SidebarSection>
      ) : null}
      {showChecklistSection ? (
        <SidebarSection label={t('categories.legacy-issues-checklists')}>
          <SidebarItem context={context} item={vehicleChecklists} />
        </SidebarSection>
      ) : null}
      {showAnalysisSection ? (
        <SidebarSection label={t('categories.legacy-issues-analysis')}>
          <SidebarItem context={context} item={assistant} />
          <SidebarItem context={context} item={assistantHistory} />
        </SidebarSection>
      ) : null}
      {showSettingsSection ? (
        <SidebarSection label={t('categories.legacy-issues-settings')}>
          {canManageDirectEditPermissions ? (
            <SidebarItem context={context} item={directEditPermissions} />
          ) : null}
          <SidebarItem context={context} item={vehicleManagement} />
          {canManageFields ? (
            <>
              <SidebarItem context={context} item={commonCode} />
              <SidebarItem context={context} item={fieldSettings} />
            </>
          ) : null}
        </SidebarSection>
      ) : null}
    </section>
  );
}

export const legacyIssuesSidebarConfig: AppSidebarConfig = {
  extendCategories: (_categories, { canReadWorkspace }) =>
    canReadWorkspace ? [LEGACY_ISSUES_CATEGORY] : [],
  renderCategory: (category, context) => {
    if (category === LEGACY_ISSUES_CATEGORY) {
      return <LegacyIssuesSidebar {...context} />;
    }
    return undefined;
  },
};
