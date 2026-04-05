import type { ColumnDef } from '@tanstack/react-table';
import type { ReactNode } from 'react';

export type Density = 'dense' | 'comfortable';

export type SidebarNavItem = {
  id: string;
  label: string;
  hint?: string;
  active?: boolean;
  onSelect?: () => void;
};

export type SidebarNavSection = {
  id: string;
  label: string;
  items: SidebarNavItem[];
};

export type DataTableColumn<TData extends object> = ColumnDef<TData, unknown>;

export type FilterOption = {
  id: string;
  label: string;
  active?: boolean;
  onSelect?: () => void;
};

export type ChartSeries = {
  key: string;
  label: string;
  color: string;
  data: number[];
};

export type DetailDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
};
