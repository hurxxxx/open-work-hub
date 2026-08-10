import { useTranslation } from 'react-i18next';
import { InlineNotice, Panel } from '@ai-do/ui';

import type { HealthCheckupPriorExamUpload } from '../api/health-checkup-api';

export function PriorExamUploadResultPanel({
  result,
}: {
  result: HealthCheckupPriorExamUpload;
}) {
  const { t } = useTranslation('apps');
  const needsReview = result.unmatched.filter(
    (item) => item.match_status === 'ambiguous',
  );
  const excluded = result.unmatched.filter(
    (item) => item.match_status === 'unmatched',
  );

  const renderRowList = (
    key: string,
    title: string,
    items: typeof result.unmatched,
    aggregateCount: number,
  ) => {
    if (aggregateCount === 0) return null;
    if (items.length === 0) {
      return <p className="m-0 text-app-text">{title}</p>;
    }
    return (
      <details>
        <summary className="cursor-pointer text-app-text">{title}</summary>
        <ul className="m-0 mt-1 pl-4">
          {items.map((item, index) => (
            <li
              key={`${key}-${item.sheet_name ?? ''}-${item.dept_name}-${item.person_name}-${index}`}
            >
              {t('healthCheckup.upload.unmatchedRow', {
                dept: item.dept_name,
                name: item.person_name,
              })}
            </li>
          ))}
        </ul>
      </details>
    );
  };

  return (
    <Panel>
      <div className="grid gap-2 p-3 text-[length:var(--ui-text-body-sm)]">
        <strong className="text-app-text">
          {t('healthCheckup.upload.resultTitle', {
            filename: result.source_filename ?? '',
          })}
        </strong>
        <span className="text-app-text-muted">
          {t('healthCheckup.upload.summary', {
            matched: result.matched_count,
            spouse: result.spouse_excluded_count,
            unmatched: result.unmatched_count,
            ambiguous: result.ambiguous_count,
          })}
        </span>
        {result.details_truncated ? (
          <InlineNotice tone="info">
            {t('healthCheckup.upload.detailsTruncated')}
          </InlineNotice>
        ) : null}

        {renderRowList(
          'needs-review',
          t('healthCheckup.upload.ambiguousListTitle', {
            count: result.ambiguous_count,
          }),
          needsReview,
          result.ambiguous_count,
        )}
        {renderRowList(
          'excluded',
          t('healthCheckup.upload.excludedListTitle', {
            count: result.unmatched_count,
          }),
          excluded,
          result.unmatched_count,
        )}

        {result.matched_count > 0 && result.matched.length === 0 ? (
          <p className="m-0 text-app-text">
            {t('healthCheckup.upload.matchedListTitle', {
              count: result.matched_count,
            })}
          </p>
        ) : null}
        {result.matched.length > 0 ? (
          <details>
            <summary className="cursor-pointer text-app-text">
              {t('healthCheckup.upload.matchedListTitle', {
                count: result.matched_count,
              })}
            </summary>
            <div className="mt-1 max-h-64 overflow-auto rounded border border-app-border">
              <table className="w-full border-collapse text-[length:var(--ui-text-caption)]">
                <thead className="sticky top-0 bg-app-surface">
                  <tr className="text-left text-app-text-muted">
                    <th className="px-2 py-1 font-medium" scope="col">
                      {t('healthCheckup.upload.colEmployeeCode')}
                    </th>
                    <th className="px-2 py-1 font-medium" scope="col">
                      {t('healthCheckup.upload.colName')}
                    </th>
                    <th className="px-2 py-1 font-medium" scope="col">
                      {t('healthCheckup.upload.colErpDept')}
                    </th>
                    <th className="px-2 py-1 font-medium" scope="col">
                      {t('healthCheckup.upload.colFileDept')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {result.matched.map((item) => {
                    const departmentDiffers =
                      item.erp_dept_name !== item.file_dept_name;
                    return (
                      <tr
                        className="border-t border-app-border"
                        key={item.employee_code}
                      >
                        <td className="px-2 py-1 text-app-text">
                          {item.employee_code}
                        </td>
                        <td className="px-2 py-1 text-app-text">
                          {item.employee_name}
                          {item.person_name !== item.employee_name ? (
                            <span className="text-app-text-muted">
                              {' ('}
                              {item.person_name}
                              {')'}
                            </span>
                          ) : null}
                        </td>
                        <td className="px-2 py-1 text-app-text">
                          {item.erp_dept_name}
                        </td>
                        <td
                          className={
                            departmentDiffers
                              ? 'px-2 py-1 font-medium text-ui-warning'
                              : 'px-2 py-1 text-app-text-muted'
                          }
                        >
                          {item.file_dept_name}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </details>
        ) : null}
      </div>
    </Panel>
  );
}
