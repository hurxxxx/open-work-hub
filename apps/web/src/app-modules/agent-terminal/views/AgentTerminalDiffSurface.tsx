import {
  MultiFileDiff,
  type MultiFileDiffProps,
  Virtualizer,
} from '@pierre/diffs/react';
import { useMemo } from 'react';

import type { AgentTerminalGitChange } from '../api/agent-terminal-api';

const DIFF_OPTIONS: NonNullable<MultiFileDiffProps<undefined>['options']> = {
  collapsedContextThreshold: 8,
  diffIndicators: 'bars',
  diffStyle: 'unified',
  disableFileHeader: true,
  expansionLineCount: 20,
  hunkSeparators: 'line-info',
  lineDiffType: 'word',
  overflow: 'wrap',
  themeType: 'system',
};

export function AgentTerminalDiffSurface({
  ariaLabel,
  diffKey,
  filePath,
  kind,
  newContent,
  oldContent,
  oldPath,
}: {
  ariaLabel: string;
  diffKey: string;
  filePath: string;
  kind: AgentTerminalGitChange['kind'];
  newContent: string;
  oldContent: string;
  oldPath?: string | null;
}) {
  const diffFiles = useMemo<MultiFileDiffProps<undefined>>(() => {
    const oldFile = {
      cacheKey: `${diffKey}:old:${contentFingerprint(oldContent)}`,
      contents: oldContent,
      name: oldPath ?? filePath,
    };
    const newFile = {
      cacheKey: `${diffKey}:new:${contentFingerprint(newContent)}`,
      contents: newContent,
      name: filePath,
    };

    if (kind === 'added' || kind === 'untracked') {
      return { newFile, oldFile: null };
    }
    if (kind === 'deleted') {
      return { newFile: null, oldFile };
    }
    return { newFile, oldFile };
  }, [diffKey, filePath, kind, newContent, oldContent, oldPath]);

  return (
    <div aria-label={ariaLabel} className="h-full min-h-0" role="region">
      <Virtualizer
        className="ui-scrollbar h-full overflow-auto"
        contentClassName="min-w-0"
      >
        <MultiFileDiff
          {...diffFiles}
          className="block min-w-0"
          disableWorkerPool
          options={DIFF_OPTIONS}
        />
      </Virtualizer>
    </div>
  );
}

function contentFingerprint(value: string): string {
  let hash = 2_166_136_261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16_777_619);
  }
  return `${value.length}:${(hash >>> 0).toString(16)}`;
}
