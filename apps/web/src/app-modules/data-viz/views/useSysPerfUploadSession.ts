import { useEffect, useMemo, useState } from 'react';

import type { SysPerfUploadedFile } from '../api/dataviz-api';
import { isUsableSysPerfUploadedFile } from './sysperf-files';
import { type PartsState } from './sysperf-parts-state';
import {
  EMPTY_COMMON,
  seedTestInfo,
  type CommonInfo,
  type FileInfo,
} from './sysperf-testinfo';

export function useSysPerfUploadSession() {
  const [uploaded, setUploaded] = useState<SysPerfUploadedFile[]>([]);
  const [selFileId, setSelFileId] = useState<number | null>(null);
  const [selSheet, setSelSheet] = useState<string>('');
  const [common, setCommon] = useState<CommonInfo>(EMPTY_COMMON);
  const [perFile, setPerFile] = useState<Record<number, FileInfo>>({});
  const [parts, setParts] = useState<Record<number, PartsState>>({});

  const usableUploaded = useMemo(
    () => uploaded.filter(isUsableSysPerfUploadedFile),
    [uploaded],
  );
  const selectedFile = useMemo(
    () => usableUploaded.find((file) => file.file_id === selFileId) ?? null,
    [usableUploaded, selFileId],
  );

  useEffect(() => {
    if (!usableUploaded.length) return;
    const seeded = seedTestInfo(usableUploaded);
    setCommon(seeded.common);
    setPerFile(seeded.perFile);
    setParts(seeded.parts);
  }, [usableUploaded]);

  return {
    uploaded,
    setUploaded,
    selFileId,
    setSelFileId,
    selSheet,
    setSelSheet,
    selectedFile,
    common,
    setCommon,
    perFile,
    setPerFile,
    parts,
    setParts,
  };
}
