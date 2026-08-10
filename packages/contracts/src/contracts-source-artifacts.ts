import path from 'node:path';

type ContractSourceArtifactFinding =
  | {
      kind: 'missing-source-directory';
      path: string;
    }
  | {
      kind: 'runtime-artifact';
      path: string;
      extension: string;
    };

export interface ContractSourceArtifactDirectoryEntry {
  name: string;
  kind: 'directory' | 'file';
}

export interface ContractSourceArtifactFileSystem {
  exists(path: string): boolean;
  readDirectory(path: string): readonly ContractSourceArtifactDirectoryEntry[];
}

interface ContractSourceArtifactScanOptions {
  sourceDir: string;
  fileSystem: ContractSourceArtifactFileSystem;
  repoRoot?: string;
  runtimeExtensions?: ReadonlySet<string> | readonly string[];
}

export const DEFAULT_CONTRACT_SOURCE_DIR = 'packages/contracts/src';

const DEFAULT_RUNTIME_ARTIFACT_EXTENSIONS = Object.freeze([
  '.js',
  '.jsx',
  '.mjs',
  '.cjs',
]);

const CONTRACT_SOURCE_ARTIFACT_POLICY_HEADER = [
  'Generated runtime artifacts are not allowed in packages/contracts/src.',
  'They can shadow the TypeScript source and make consumers import stale Interfaces.',
];

export function scanContractSourceArtifacts({
  sourceDir,
  fileSystem,
  repoRoot = process.cwd(),
  runtimeExtensions = DEFAULT_RUNTIME_ARTIFACT_EXTENSIONS,
}: ContractSourceArtifactScanOptions): ContractSourceArtifactFinding[] {
  if (!fileSystem.exists(sourceDir)) {
    return [
      {
        kind: 'missing-source-directory',
        path: toRepoRelativePath(sourceDir, repoRoot),
      },
    ];
  }

  const runtimeExtensionSet = toRuntimeExtensionSet(runtimeExtensions);
  const findings = walkContractSourceFiles(sourceDir, fileSystem)
    .filter((filePath) =>
      isGeneratedRuntimeArtifact(filePath, runtimeExtensionSet),
    )
    .map<ContractSourceArtifactFinding>((filePath) => ({
      kind: 'runtime-artifact',
      path: toRepoRelativePath(filePath, repoRoot),
      extension: runtimeArtifactExtension(filePath),
    }))
    .sort((left, right) => left.path.localeCompare(right.path));

  return findings;
}

export function formatContractSourceArtifactReport(
  findings: readonly ContractSourceArtifactFinding[],
): string | null {
  if (findings.length === 0) {
    return null;
  }

  const missingSourceDir = findings.find(
    (finding) => finding.kind === 'missing-source-directory',
  );
  if (missingSourceDir) {
    return `Contracts source directory does not exist: ${missingSourceDir.path}`;
  }

  return [
    ...CONTRACT_SOURCE_ARTIFACT_POLICY_HEADER,
    ...findings.map((finding) => `- ${finding.path}`),
  ].join('\n');
}

export function isContractSourceArtifactCheckPassing(
  findings: readonly ContractSourceArtifactFinding[],
): boolean {
  return findings.length === 0;
}

function walkContractSourceFiles(
  dir: string,
  fileSystem: ContractSourceArtifactFileSystem,
): string[] {
  const files: string[] = [];
  for (const entry of fileSystem.readDirectory(dir)) {
    const fullPath = path.join(dir, entry.name);
    if (entry.kind === 'directory') {
      files.push(...walkContractSourceFiles(fullPath, fileSystem));
    } else if (entry.kind === 'file') {
      files.push(fullPath);
    }
  }
  return files;
}

function isGeneratedRuntimeArtifact(
  filePath: string,
  runtimeExtensions: ReadonlySet<string>,
): boolean {
  return runtimeExtensions.has(runtimeArtifactExtension(filePath));
}

function runtimeArtifactExtension(filePath: string): string {
  if (filePath.endsWith('.map')) {
    return path.extname(filePath.slice(0, -4));
  }
  return path.extname(filePath);
}

function toRuntimeExtensionSet(
  runtimeExtensions: ReadonlySet<string> | readonly string[],
): ReadonlySet<string> {
  return runtimeExtensions instanceof Set
    ? runtimeExtensions
    : new Set(runtimeExtensions);
}

function toRepoRelativePath(filePath: string, repoRoot: string): string {
  return path.relative(repoRoot, filePath).split(path.sep).join('/');
}
