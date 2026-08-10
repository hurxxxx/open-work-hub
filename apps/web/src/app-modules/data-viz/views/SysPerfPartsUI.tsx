import { useTranslation } from 'react-i18next';

import {
  PART_CAT_LABELS,
  PART_CAT_ORDER,
  COMPETITOR_SUBTYPE,
  DEFAULT_PART_TYPE,
  NONE_OPTION,
  LBL_COLORS,
  PART_TYPES,
  PART_TYPE_COLORS,
  type PartCatalogTree,
  compDisplayGroups,
  partItems,
} from './sysperf-parts';
import type { PartSel, PartsState } from './sysperf-parts-state';
import { SYSPERF_PARTS_UI_COLORS } from './data-viz-colors';

export function SysPerfPartsSelect({
  catalog,
  value,
  onChange,
}: {
  catalog: PartCatalogTree;
  value: PartsState;
  onChange: (partKey: string, patch: Partial<PartSel>) => void;
}) {
  const { t } = useTranslation('apps');
  const Chip = ({
    partKey,
    name,
    none,
  }: {
    partKey: string;
    name: string;
    none?: boolean;
  }) => {
    const sel = value[partKey]?.selected === name;
    const base: React.CSSProperties = none
      ? {
          padding: '5px 12px',
          border: SYSPERF_PARTS_UI_COLORS.noneBorder,
          borderRadius: 14,
          background: SYSPERF_PARTS_UI_COLORS.noneBg,
          color: SYSPERF_PARTS_UI_COLORS.noneText,
          fontSize: 15,
          fontStyle: 'italic',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }
      : {
          padding: '5px 12px',
          border: SYSPERF_PARTS_UI_COLORS.chipBorder,
          borderRadius: 14,
          background: SYSPERF_PARTS_UI_COLORS.chipBg,
          fontSize: 15,
          fontWeight: 500,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        };
    const selStyle: React.CSSProperties = sel
      ? {
          background: SYSPERF_PARTS_UI_COLORS.selectedBg,
          color: SYSPERF_PARTS_UI_COLORS.white,
          borderColor: SYSPERF_PARTS_UI_COLORS.selectedBg,
        }
      : {};
    return (
      <button
        type="button"
        onClick={() => onChange(partKey, { selected: name, direct: name })}
        style={{ ...base, ...selStyle }}
      >
        {name}
      </button>
    );
  };

  const Label = ({ label }: { label: string }) => {
    const col = LBL_COLORS[label] || {
      bg: SYSPERF_PARTS_UI_COLORS.labelFallbackBg,
      fg: SYSPERF_PARTS_UI_COLORS.labelFallbackFg,
      bd: SYSPERF_PARTS_UI_COLORS.labelFallbackBorder,
    };
    return (
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 92,
          fontSize: 15,
          fontWeight: 700,
          color: col.fg,
          background: col.bg,
          border: `1px solid ${col.bd}`,
          padding: '6px 12px',
          borderRadius: 12,
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </span>
    );
  };

  return (
    <div className="flex flex-col">
      {PART_CAT_ORDER.map((partKey) => {
        const compGroups = partKey === 'comp' ? compDisplayGroups(catalog) : [];
        const list = partKey === 'comp' ? [] : partItems(catalog, partKey);
        const v = value[partKey] || {
          selected: '',
          direct: '',
          type: DEFAULT_PART_TYPE,
        };
        return (
          <div
            key={partKey}
            className="flex items-start gap-2 border-b border-app-border/60 py-2.5"
          >
            <span className="app-text-body-sm w-24 shrink-0 pt-1.5 font-semibold text-app-ink">
              {PART_CAT_LABELS[partKey]}
            </span>
            <div className="flex flex-1 flex-col gap-1">
              {partKey === 'comp' ? (
                compGroups.map((g) => {
                  const isLast = g.label === COMPETITOR_SUBTYPE;
                  if (!g.items.length && !isLast) return null;
                  return (
                    <div
                      key={g.label}
                      className="flex w-full flex-wrap items-center gap-1"
                    >
                      <Label label={g.label} />
                      {g.items.map((it) => (
                        <Chip key={it.id} partKey="comp" name={it.name} />
                      ))}
                      {isLast ? (
                        <Chip partKey="comp" name={NONE_OPTION} none />
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <div className="flex flex-wrap items-center gap-1">
                  {list.map((it) => (
                    <Chip key={it.id} partKey={partKey} name={it.name} />
                  ))}
                  <Chip partKey={partKey} name={NONE_OPTION} none />
                </div>
              )}
            </div>
            <input
              type="text"
              placeholder={t('ai.dataViz.sysPerf.parts.directPlaceholder')}
              value={v.direct}
              onChange={(e) => onChange(partKey, { direct: e.target.value })}
              className="app-text-body-sm w-40 shrink-0 rounded-md border border-app-border bg-app-bg px-2 py-1.5 text-app-ink outline-none focus:border-app-accent"
            />
            <span className="flex shrink-0 gap-1">
              {PART_TYPES.map((t) => {
                const active = v.type === t;
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => onChange(partKey, { type: t })}
                    className="rounded-md border-2 px-2.5 py-1 font-bold transition-colors"
                    style={{
                      fontSize: 13,
                      color: PART_TYPE_COLORS[t],
                      borderColor: active
                        ? PART_TYPE_COLORS[t]
                        : SYSPERF_PARTS_UI_COLORS.inactiveBorder,
                      background: active
                        ? `${PART_TYPE_COLORS[t]}18`
                        : SYSPERF_PARTS_UI_COLORS.white,
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </span>
          </div>
        );
      })}
    </div>
  );
}
