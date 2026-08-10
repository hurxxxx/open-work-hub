import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import { CAT_COLORS } from './sysperf-items';
import type { SysPerfAvgMode, SysPerfMatchRowView } from './sysperf-match';
import type { UsableSysPerfUploadedFile } from './sysperf-files';
import { SYSPERF_MATCH_GRID_COLORS as GRID_COLORS } from './data-viz-colors';

const B = GRID_COLORS.border;
const SC = 4;

export function SysPerfMatchGrid({
  files,
  rows,
  activeFileId,
  headersByFileId,
  collapsedGroups,
  avgMode,
  targetTemp,
  onTargetTempChange,
  onToggleCollapse,
  onToggleAvgMode,
  onCheckChange,
  onAltChange,
}: {
  files: UsableSysPerfUploadedFile[];
  rows: SysPerfMatchRowView[];
  activeFileId: number | null;
  headersByFileId: Record<number, string[]>;
  collapsedGroups: Set<string>;
  avgMode: Record<number, SysPerfAvgMode>;
  targetTemp: string;
  onTargetTempChange: (value: string) => void;
  onToggleCollapse: (group: string) => void;
  onToggleAvgMode: (itemN: number) => void;
  onCheckChange: (fileId: number, itemN: number, checked: boolean) => void;
  onAltChange: (fileId: number, itemN: number, value: string) => void;
}) {
  const { t } = useTranslation('apps');
  const fileColVisible = (fileId: number) =>
    files.length < 2 || activeFileId === fileId;

  return (
    <div
      style={{
        overflow: 'auto',
        maxHeight: '72vh',
        border: GRID_COLORS.outerBorder,
        borderRadius: 4,
      }}
    >
      <table
        style={{
          borderCollapse: 'collapse',
          fontSize: 14,
          tableLayout: 'fixed',
        }}
      >
        <thead style={{ position: 'sticky', top: 0, zIndex: 2 }}>
          <tr
            style={{
              background: GRID_COLORS.primaryHeader,
              color: GRID_COLORS.white,
              fontWeight: 700,
              fontSize: 15,
            }}
          >
            <th rowSpan={2} style={{ border: B, padding: 6, width: 109 }}>
              {t('ai.dataViz.sysPerf.match.headers.category')}
            </th>
            <th rowSpan={2} style={{ border: B, padding: 6, width: 439 }}>
              {t('ai.dataViz.sysPerf.match.headers.item')}
            </th>
            <th rowSpan={2} style={{ border: B, padding: 6, width: 122 }}>
              {t('ai.dataViz.sysPerf.match.headers.unit')}
            </th>
            {files.map((file) =>
              fileColVisible(file.file_id) ? (
                <th
                  key={file.file_id}
                  colSpan={SC}
                  style={{ border: B, padding: 6, textAlign: 'center' }}
                >
                  {t('ai.dataViz.sysPerf.match.headers.dataList')}
                </th>
              ) : null,
            )}
            <th
              rowSpan={2}
              style={{
                border: B,
                padding: 6,
                width: 143,
                fontSize: 13,
                lineHeight: 1.2,
              }}
            >
              {t('ai.dataViz.sysPerf.match.headers.match')}
              <br />
              {t('ai.dataViz.sysPerf.match.headers.success')}
            </th>
          </tr>
          <tr
            style={{
              background: GRID_COLORS.secondaryHeader,
              color: GRID_COLORS.white,
              fontSize: 15,
              fontWeight: 700,
            }}
          >
            {files.map((file) => {
              if (!fileColVisible(file.file_id)) return null;
              const shortName =
                file.filename.length > 15
                  ? `${file.filename.substring(0, 15)}…`
                  : file.filename;
              return (
                <Fragment key={file.file_id}>
                  <th
                    style={{
                      border: B,
                      padding: 6,
                      background: GRID_COLORS.fileHeader,
                      width: 452,
                      fontSize: 15,
                    }}
                  >
                    {shortName}
                  </th>
                  <th
                    style={{
                      border: B,
                      padding: 6,
                      width: 127,
                      background: GRID_COLORS.fileHeader,
                      fontSize: 12,
                    }}
                  >
                    {t('ai.dataViz.sysPerf.match.headers.autoCheck')}
                  </th>
                  <th
                    style={{
                      border: B,
                      padding: 6,
                      background: GRID_COLORS.fileHeader,
                      width: 447,
                      fontSize: 15,
                    }}
                  >
                    {t('ai.dataViz.sysPerf.match.headers.alternative')}
                  </th>
                  <th
                    style={{
                      border: B,
                      padding: 6,
                      width: 127,
                      background: GRID_COLORS.fileHeader,
                      fontSize: 15,
                    }}
                  >
                    {t('ai.dataViz.sysPerf.match.headers.data')}
                  </th>
                </Fragment>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const { item, depth } = row;
            const leftPad = 8 + depth * 20;
            const fontSz = depth === 0 ? 14 : depth === 1 ? 13 : 12;
            const textColor =
              depth === 0 ? GRID_COLORS.text : GRID_COLORS.mutedText;
            const avgGroup = row.avgGroup;
            return (
              <tr
                key={item.n}
                style={{ background: GRID_COLORS.row, height: 30 }}
              >
                {row.showCategory ? (
                  <td
                    rowSpan={row.categoryRowSpan}
                    style={{
                      border: B,
                      padding: 4,
                      textAlign: 'center',
                      verticalAlign: 'middle',
                      fontWeight: 700,
                      fontSize: 15,
                      color: GRID_COLORS.white,
                      background:
                        CAT_COLORS[item.c || ''] ||
                        GRID_COLORS.categoryFallback,
                      whiteSpace: 'pre-line',
                      lineHeight: 1.3,
                      wordBreak: 'keep-all',
                    }}
                  >
                    {item.c || ''}
                  </td>
                ) : null}
                <td
                  style={{
                    border: B,
                    padding: 4,
                    paddingLeft: leftPad,
                    fontSize: fontSz,
                    color: textColor,
                    fontWeight: depth === 0 ? 500 : undefined,
                    overflow: 'hidden',
                    maxWidth: 100,
                  }}
                >
                  {item.nm}
                  {avgGroup ? (
                    <>
                      <button
                        type="button"
                        onClick={() => onToggleCollapse(avgGroup)}
                        style={{
                          float: 'right',
                          cursor: 'pointer',
                          fontSize: 16,
                          fontWeight: 700,
                          background: GRID_COLORS.primaryHeader,
                          color: GRID_COLORS.white,
                          border: 'none',
                          borderRadius: 4,
                          width: 24,
                          height: 24,
                          lineHeight: '22px',
                          padding: 0,
                          marginLeft: 4,
                        }}
                      >
                        {collapsedGroups.has(avgGroup) ? '+' : '-'}
                      </button>
                      <button
                        type="button"
                        onClick={() => onToggleAvgMode(item.n)}
                        title={t('ai.dataViz.sysPerf.match.toggleAverageMode')}
                        style={{
                          float: 'right',
                          cursor: 'pointer',
                          fontSize: 12,
                          fontWeight: 600,
                          background:
                            (avgMode[item.n] || 'direct') === 'direct'
                              ? GRID_COLORS.direct
                              : GRID_COLORS.average,
                          color: GRID_COLORS.white,
                          border: 'none',
                          borderRadius: 4,
                          padding: '2px 8px',
                          marginLeft: 4,
                          height: 24,
                        }}
                      >
                        {(avgMode[item.n] || 'direct') === 'direct'
                          ? t('ai.dataViz.sysPerf.match.directValue')
                          : t('ai.dataViz.sysPerf.match.averageValue')}
                      </button>
                    </>
                  ) : null}
                </td>
                <td
                  style={{
                    border: B,
                    padding: 4,
                    textAlign: 'center',
                    fontSize: 13,
                    color: GRID_COLORS.categoryFallback,
                  }}
                >
                  {item.u}
                </td>

                {row.kind === 'target'
                  ? row.fileCells.map((cell) =>
                      cell.visible ? (
                        <td
                          key={cell.fileId}
                          colSpan={SC}
                          style={{ border: B, padding: 4 }}
                        >
                          <input
                            type="number"
                            step="0.1"
                            placeholder={t(
                              'ai.dataViz.sysPerf.match.targetTempPlaceholder',
                            )}
                            value={targetTemp}
                            onChange={(event) =>
                              onTargetTempChange(event.target.value)
                            }
                            style={{
                              width: 120,
                              padding: '4px 8px',
                              border: GRID_COLORS.inputBorder,
                              borderRadius: 4,
                              fontSize: 14,
                            }}
                          />
                        </td>
                      ) : null,
                    )
                  : row.kind === 'calculated'
                    ? row.fileCells.map((cell) =>
                        cell.visible ? (
                          <Fragment key={`${cell.fileId}-calc`}>
                            <td
                              style={{
                                border: B,
                                padding: '4px 6px',
                                fontSize: 13,
                                background: GRID_COLORS.calculatedBg,
                                color: GRID_COLORS.calculatedText,
                                fontStyle: 'italic',
                              }}
                            >
                              {t('ai.dataViz.sysPerf.match.calculatedValue')}
                            </td>
                            <td
                              style={{
                                border: B,
                                padding: 3,
                                textAlign: 'center',
                              }}
                            >
                              —
                            </td>
                            <td
                              style={{
                                border: B,
                                padding: 3,
                                textAlign: 'center',
                                color: GRID_COLORS.disabledText,
                                fontSize: 12,
                              }}
                            >
                              {t('ai.dataViz.sysPerf.match.autoCalculated')}
                            </td>
                            <td
                              style={{
                                border: B,
                                padding: 4,
                                textAlign: 'center',
                                fontSize: 12,
                                color: GRID_COLORS.calculatedText,
                                background: GRID_COLORS.calculatedBg,
                                fontStyle: 'italic',
                              }}
                            >
                              {t('ai.dataViz.sysPerf.match.calculatedValue')}
                            </td>
                          </Fragment>
                        ) : null,
                      )
                    : row.fileCells.map((cell) => {
                        if (!cell.visible) return null;
                        const avgDisabled = cell.averageDisabled;
                        const cur = cell.currentMatch;
                        const vs = cell.valueState;
                        return (
                          <Fragment key={`${cell.fileId}-match`}>
                            <td
                              style={{
                                border: B,
                                padding: '4px 6px',
                                fontSize: 13,
                                background: avgDisabled
                                  ? GRID_COLORS.subAverageBg
                                  : cur
                                    ? GRID_COLORS.successBg
                                    : '',
                              }}
                            >
                              {avgDisabled ? (
                                <span
                                  style={{
                                    color: GRID_COLORS.average,
                                    fontStyle: 'italic',
                                    fontSize: 12,
                                  }}
                                >
                                  {t('ai.dataViz.sysPerf.match.subAverage')}
                                </span>
                              ) : (
                                cur
                              )}
                            </td>
                            <td
                              style={{
                                border: B,
                                padding: 3,
                                textAlign: 'center',
                              }}
                            >
                              <input
                                type="checkbox"
                                disabled={avgDisabled}
                                checked={cell.checked}
                                onChange={(event) =>
                                  onCheckChange(
                                    cell.fileId,
                                    item.n,
                                    event.target.checked,
                                  )
                                }
                                style={{ width: 16, height: 16 }}
                              />
                            </td>
                            <td style={{ border: B, padding: 3 }}>
                              <select
                                disabled={avgDisabled}
                                value=""
                                onChange={(event) =>
                                  onAltChange(
                                    cell.fileId,
                                    item.n,
                                    event.target.value,
                                  )
                                }
                                className="app-field-input-sm"
                              >
                                <option value="">—</option>
                                {(headersByFileId[cell.fileId] ?? []).map(
                                  (header, headerIndex) => (
                                    <option
                                      key={`${header}-${headerIndex}`}
                                      value={header}
                                    >
                                      {header}
                                    </option>
                                  ),
                                )}
                              </select>
                            </td>
                            <td
                              style={{
                                border: B,
                                padding: 4,
                                textAlign: 'right',
                                fontSize: 13,
                                background:
                                  vs === 'ok'
                                    ? GRID_COLORS.successBg
                                    : vs === 'nodata'
                                      ? GRID_COLORS.noDataBg
                                      : '',
                              }}
                            >
                              {vs === 'loading' ? (
                                <span
                                  style={{
                                    color: GRID_COLORS.subtleText,
                                    fontSize: 12,
                                  }}
                                >
                                  ...
                                </span>
                              ) : null}
                              {vs === 'nodata' ? (
                                <span
                                  style={{
                                    color: GRID_COLORS.danger,
                                    fontSize: 12,
                                  }}
                                >
                                  {t('ai.dataViz.sysPerf.match.noData')}
                                </span>
                              ) : null}
                              {vs === 'qmark' ? (
                                <span
                                  style={{
                                    color: GRID_COLORS.subtleText,
                                    fontSize: 12,
                                  }}
                                >
                                  ?
                                </span>
                              ) : null}
                              {vs === 'err' ? (
                                <span
                                  style={{
                                    color: GRID_COLORS.average,
                                    fontSize: 12,
                                  }}
                                >
                                  {t('ai.dataViz.sysPerf.match.error')}
                                </span>
                              ) : null}
                            </td>
                          </Fragment>
                        );
                      })}

                <td
                  style={{
                    border: B,
                    padding: 3,
                    textAlign: 'center',
                    background: row.success ? GRID_COLORS.successBg : '',
                    fontSize: 14,
                  }}
                >
                  {row.success ? '✅' : ''}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
