#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { createJiti } from 'jiti';

const jiti = createJiti(import.meta.url);
const {
  DEFAULT_CONTRACT_SOURCE_DIR,
  formatContractSourceArtifactReport,
  scanContractSourceArtifacts,
} = await jiti.import('../packages/contracts/src/contracts-source-artifacts.ts');

const DEFAULT_SOURCE_DIR = path.join(process.cwd(), DEFAULT_CONTRACT_SOURCE_DIR);

export { formatContractSourceArtifactReport, scanContractSourceArtifacts };

const nodeFileSystem = {
  exists(filePath) {
    return fs.existsSync(filePath);
  },
  readDirectory(dir) {
    return fs
      .readdirSync(dir, { withFileTypes: true })
      .flatMap((entry) => {
        if (entry.isDirectory()) {
          return [{ name: entry.name, kind: 'directory' }];
        }
        if (entry.isFile()) {
          return [{ name: entry.name, kind: 'file' }];
        }
        return [];
      });
  },
};

export function findContractSourceArtifacts({
  sourceDir = DEFAULT_SOURCE_DIR,
  repoRoot = process.cwd(),
  fileSystem = nodeFileSystem,
} = {}) {
  const findings = scanContractSourceArtifacts({
    sourceDir,
    fileSystem,
    repoRoot,
  });
  const missingSourceDir = findings.find(
    (finding) => finding.kind === 'missing-source-directory',
  );
  if (missingSourceDir) {
    throw new Error(`Contracts source directory does not exist: ${sourceDir}`);
  }
  return findings
    .filter((finding) => finding.kind === 'runtime-artifact')
    .map((finding) => finding.path);
}

export function checkContractSourceArtifacts({
  sourceDir = DEFAULT_SOURCE_DIR,
  repoRoot = process.cwd(),
  fileSystem = nodeFileSystem,
} = {}) {
  const findings = scanContractSourceArtifacts({
    sourceDir,
    fileSystem,
    repoRoot,
  });
  const report = formatContractSourceArtifactReport(findings);
  const missingSourceDir = findings.find(
    (finding) => finding.kind === 'missing-source-directory',
  );
  if (missingSourceDir) {
    throw new Error(`Contracts source directory does not exist: ${sourceDir}`);
  }
  if (report) {
    throw new Error(report);
  }
  return findings;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    checkContractSourceArtifacts();
    console.log('Contracts source runtime artifact check passed.');
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
