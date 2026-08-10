type OpfsDirectoryHandle = {
  getDirectoryHandle: (
    name: string,
    options?: { create?: boolean },
  ) => Promise<OpfsDirectoryHandle>;
  getFileHandle: (
    name: string,
    options?: { create?: boolean },
  ) => Promise<OpfsFileHandle>;
  removeEntry: (name: string, options?: { recursive?: boolean }) => Promise<void>;
};

type OpfsFileHandle = {
  createWritable: () => Promise<{
    write: (data: Blob | BufferSource | string) => Promise<void>;
    close: () => Promise<void>;
  }>;
  getFile: () => Promise<File>;
};

type NavigatorWithOpfs = Navigator & {
  storage?: StorageManager & {
    getDirectory?: () => Promise<OpfsDirectoryHandle>;
  };
};

const RECORDING_OPFS_ROOT = 'open-work-hub-recording';

function opfsNavigator(): NavigatorWithOpfs | null {
  if (typeof navigator === 'undefined') {
    return null;
  }
  return navigator as NavigatorWithOpfs;
}

function chunkFilename(seq: number): string {
  return `${String(seq).padStart(8, '0')}.chunk`;
}

async function recordingRoot(create: boolean): Promise<OpfsDirectoryHandle | null> {
  const root = await opfsNavigator()?.storage?.getDirectory?.();
  if (!root) {
    return null;
  }
  return root.getDirectoryHandle(RECORDING_OPFS_ROOT, { create });
}

async function sessionDirectory(
  stagingId: string,
  create: boolean,
): Promise<OpfsDirectoryHandle | null> {
  const root = await recordingRoot(create);
  if (!root) {
    return null;
  }
  return root.getDirectoryHandle(stagingId, { create });
}

export async function writeOpfsChunk(stagingId: string, seq: number, blob: Blob): Promise<string | null> {
  try {
    const dir = await sessionDirectory(stagingId, true);
    if (!dir) {
      return null;
    }
    const filename = chunkFilename(seq);
    const file = await dir.getFileHandle(filename, { create: true });
    const writable = await file.createWritable();
    await writable.write(blob);
    await writable.close();
    return filename;
  } catch {
    return null;
  }
}

export async function readOpfsChunk(stagingId: string, path: string): Promise<Blob | null> {
  try {
    const dir = await sessionDirectory(stagingId, false);
    const file = await dir?.getFileHandle(path);
    return await file?.getFile() ?? null;
  } catch {
    return null;
  }
}

export async function deleteOpfsSession(stagingId: string): Promise<void> {
  try {
    const root = await recordingRoot(false);
    await root?.removeEntry(stagingId, { recursive: true });
  } catch {
    return;
  }
}
