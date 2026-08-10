#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const LEGACY_CHECKOUT_BASE = '/projects/ai-do-';

const DEFAULT_LEGACY_PATHS = ['prod', 'dev'].map(
  (suffix) => `${LEGACY_CHECKOUT_BASE}${suffix}`,
);
const DEFAULT_EXCLUDED_PATH_PREFIXES = ['learning/', 'docs/reference/'];
export const FAILURE_MESSAGE =
  'Found legacy checkout path references outside excluded reference docs.';

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function buildLegacyPathPattern(legacyPaths = DEFAULT_LEGACY_PATHS) {
  if (!legacyPaths.length) {
    throw new Error('buildLegacyPathPattern requires at least one legacy path.');
  }

  const alternates = legacyPaths.map((legacyPath) => escapeRegExp(legacyPath)).join('|');
  return new RegExp(`(${alternates})([^A-Za-z0-9_-]|$)`);
}

function normalizeRepoPath(filePath) {
  return filePath.replace(/\\/g, '/').replaceAll(path.sep, '/').replace(/^\.\//, '');
}

export function isExcludedPath(
  filePath,
  excludedPathPrefixes = DEFAULT_EXCLUDED_PATH_PREFIXES,
) {
  const normalizedPath = normalizeRepoPath(filePath);

  return excludedPathPrefixes.some((rawPrefix) => {
    const normalizedPrefix = normalizeRepoPath(rawPrefix).replace(/^\/+/, '');
    const directoryPrefix = normalizedPrefix.endsWith('/')
      ? normalizedPrefix
      : `${normalizedPrefix}/`;
    const directoryPath = directoryPrefix.slice(0, -1);

    return normalizedPath === directoryPath || normalizedPath.startsWith(directoryPrefix);
  });
}

function legacyPathsInLine(line, pattern) {
  const linePattern = new RegExp(pattern.source, 'g');
  const legacyPaths = [];

  for (const match of line.matchAll(linePattern)) {
    const legacyPath = match[1];
    if (!legacyPaths.includes(legacyPath)) {
      legacyPaths.push(legacyPath);
    }
  }

  return legacyPaths;
}

export function findLegacyPathReferences({
  files,
  readFile,
  excludedPathPrefixes = DEFAULT_EXCLUDED_PATH_PREFIXES,
  legacyPaths = DEFAULT_LEGACY_PATHS,
} = {}) {
  if (!files) {
    throw new Error('findLegacyPathReferences requires a files array.');
  }
  if (!readFile) {
    throw new Error('findLegacyPathReferences requires a readFile function.');
  }

  const pattern = buildLegacyPathPattern(legacyPaths);
  const findings = [];

  for (const file of files) {
    if (isExcludedPath(file, excludedPathPrefixes)) {
      continue;
    }

    const source = readFile(file);
    const lines = source.split(/\r?\n/);

    for (const [lineIndex, lineText] of lines.entries()) {
      const matchedLegacyPaths = legacyPathsInLine(lineText, pattern);
      if (matchedLegacyPaths.length === 0) {
        continue;
      }

      findings.push({
        file,
        line: lineIndex + 1,
        lineText,
        legacyPaths: matchedLegacyPaths,
      });
    }
  }

  return findings;
}

function displayPath(filePath, repoRoot) {
  if (repoRoot && path.isAbsolute(filePath)) {
    return normalizeRepoPath(path.relative(repoRoot, filePath));
  }

  return normalizeRepoPath(filePath);
}

export function formatPathHardcodingFindings(findings, { repoRoot = null } = {}) {
  return findings
    .map((finding) => {
      const filePath = displayPath(finding.file, repoRoot);
      return `${filePath}:${finding.line}:${finding.lineText}`;
    })
    .join('\n');
}

function resolveRepoFile(repoRoot, filePath) {
  return path.isAbsolute(filePath) ? filePath : path.join(repoRoot, filePath);
}

function collectGitTrackedFiles(repoRoot = process.cwd()) {
  const output = execFileSync('git', ['ls-files', '-z', '--', '.'], {
    cwd: repoRoot,
    encoding: 'buffer',
  });

  return output.toString('utf8').split('\0').filter(Boolean);
}

function runPathHardcodingCheck(repoRoot = process.cwd(), options = {}) {
  const files = options.files ?? collectGitTrackedFiles(repoRoot);
  const scanFiles = options.readFile
    ? files
    : files.filter((file) => fs.existsSync(resolveRepoFile(repoRoot, file)));
  const readFile =
    options.readFile ??
    ((file) => fs.readFileSync(resolveRepoFile(repoRoot, file), 'utf8'));

  const findings = findLegacyPathReferences({
    files: scanFiles,
    readFile,
    excludedPathPrefixes: options.excludedPathPrefixes ?? DEFAULT_EXCLUDED_PATH_PREFIXES,
    legacyPaths: options.legacyPaths ?? DEFAULT_LEGACY_PATHS,
  });

  return {
    ok: findings.length === 0,
    findings,
    repoRoot,
  };
}

export function runCli(options = {}) {
  const cwd = options.cwd ?? process.cwd();
  const stdout = options.stdout ?? console.log;
  const stderr = options.stderr ?? console.error;

  try {
    const result = runPathHardcodingCheck(cwd, options);

    if (!result.ok) {
      stdout(formatPathHardcodingFindings(result.findings, { repoRoot: result.repoRoot }));
      stderr(FAILURE_MESSAGE);
      return 1;
    }

    return 0;
  } catch (error) {
    stderr(`Unable to check path hardcoding: ${error.message}`);
    return 2;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = runCli();
}
