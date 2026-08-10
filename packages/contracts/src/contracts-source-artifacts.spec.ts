import path from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  formatContractSourceArtifactReport,
  isContractSourceArtifactCheckPassing,
  scanContractSourceArtifacts,
  type ContractSourceArtifactDirectoryEntry,
  type ContractSourceArtifactFileSystem,
} from './contracts-source-artifacts';

describe('contracts source artifact check', () => {
  it('accepts TypeScript source and declaration files', () => {
    const fileSystem = memoryFileSystem({
      'index.ts': 'export {};',
      'openapi.generated.d.ts': 'export type paths = {};',
    });

    const findings = scanContractSourceArtifacts({
      sourceDir: repoPath('packages/contracts/src'),
      fileSystem,
      repoRoot: repoPath('.'),
    });

    expect(findings).toEqual([]);
    expect(isContractSourceArtifactCheckPassing(findings)).toBe(true);
    expect(formatContractSourceArtifactReport(findings)).toBeNull();
  });

  it('rejects runtime JavaScript artifacts that can shadow TypeScript source', () => {
    const fileSystem = memoryFileSystem({
      'api.ts': 'export {};',
      'api.js': 'module.exports = {};',
      'dm.js.map': '{}',
      'nested/model.cjs': 'module.exports = {};',
    });

    const findings = scanContractSourceArtifacts({
      sourceDir: repoPath('packages/contracts/src'),
      fileSystem,
      repoRoot: repoPath('.'),
    });

    expect(findings).toEqual([
      {
        kind: 'runtime-artifact',
        path: 'packages/contracts/src/api.js',
        extension: '.js',
      },
      {
        kind: 'runtime-artifact',
        path: 'packages/contracts/src/dm.js.map',
        extension: '.js',
      },
      {
        kind: 'runtime-artifact',
        path: 'packages/contracts/src/nested/model.cjs',
        extension: '.cjs',
      },
    ]);
    expect(isContractSourceArtifactCheckPassing(findings)).toBe(false);
    expect(formatContractSourceArtifactReport(findings)).toBe(
      [
        'Generated runtime artifacts are not allowed in packages/contracts/src.',
        'They can shadow the TypeScript source and make consumers import stale Interfaces.',
        '- packages/contracts/src/api.js',
        '- packages/contracts/src/dm.js.map',
        '- packages/contracts/src/nested/model.cjs',
      ].join('\n'),
    );
  });

  it('reports a missing source directory as a policy finding', () => {
    const fileSystem = memoryFileSystem({}, { includeRoot: false });
    const findings = scanContractSourceArtifacts({
      sourceDir: repoPath('packages/contracts/src'),
      fileSystem,
      repoRoot: repoPath('.'),
    });

    expect(findings).toEqual([
      {
        kind: 'missing-source-directory',
        path: 'packages/contracts/src',
      },
    ]);
    expect(formatContractSourceArtifactReport(findings)).toBe(
      'Contracts source directory does not exist: packages/contracts/src',
    );
  });
});

function memoryFileSystem(
  files: Record<string, string>,
  { includeRoot = true }: { includeRoot?: boolean } = {},
): ContractSourceArtifactFileSystem {
  const root = repoPath('packages/contracts/src');
  const directories = new Set<string>(includeRoot ? [root] : []);
  const filePaths = new Set<string>();

  for (const relativePath of Object.keys(files)) {
    const filePath = path.join(root, relativePath);
    filePaths.add(filePath);

    let currentDir = path.dirname(filePath);
    while (!directories.has(currentDir)) {
      directories.add(currentDir);
      currentDir = path.dirname(currentDir);
    }
  }

  return {
    exists(filePath) {
      return directories.has(filePath) || filePaths.has(filePath);
    },
    readDirectory(dir) {
      const childDirectories = new Set<string>();
      const entries: ContractSourceArtifactDirectoryEntry[] = [];

      for (const filePath of filePaths) {
        const relativePath = path.relative(dir, filePath);
        if (relativePath === '' || relativePath.startsWith('..')) {
          continue;
        }

        const [firstSegment, ...rest] = relativePath.split(path.sep);
        if (rest.length === 0) {
          entries.push({ name: firstSegment, kind: 'file' });
        } else if (!childDirectories.has(firstSegment)) {
          childDirectories.add(firstSegment);
          entries.push({ name: firstSegment, kind: 'directory' });
        }
      }

      return entries.sort((left, right) => left.name.localeCompare(right.name));
    },
  };
}

function repoPath(relativePath: string): string {
  return path.resolve('/repo', relativePath);
}
