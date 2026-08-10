import type { SysPerfSheetInfo, SysPerfUploadedFile } from '../api/dataviz-api';

export type UsableSysPerfUploadedFile = SysPerfUploadedFile & {
  file_id: number;
  sheets: [SysPerfSheetInfo, ...SysPerfSheetInfo[]];
};

export function isUsableSysPerfUploadedFile(
  file: SysPerfUploadedFile,
): file is UsableSysPerfUploadedFile {
  return (
    !file.error &&
    typeof file.file_id === 'number' &&
    Array.isArray(file.sheets) &&
    file.sheets.length > 0
  );
}
