#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const internalSegments = new Set(['api', 'lib', 'model', 'pages', 'routes', 'sidebar', 'ui', 'views']);
const appModuleRootAliasPattern = /^@\/src\/app-modules\/[^/]+$/;
const publicAppModuleAliasPattern = /^@\/src\/app-modules\/[^/]+(?:\/extension-metadata|\/extension-registration|\/manifest|\/public-api)?$/;
const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']);
const skippedDirectories = new Set(['node_modules', 'dist']);

export function createBoundaryPaths(repoRoot) {
  const resolvedRepoRoot = path.resolve(repoRoot);
  const webSrcRoot = path.join(resolvedRepoRoot, 'apps/web/src');
  const appModulesRoot = path.join(webSrcRoot, 'app-modules');

  return {
    repoRoot: resolvedRepoRoot,
    webSrcRoot,
    appModulesRoot,
  };
}

export function toPosix(filePath) {
  return filePath.split(path.sep).join('/');
}

export function parseAppModulePath(filePath, options) {
  const appModulesRoot = typeof options === 'string' ? options : options?.appModulesRoot;
  if (!appModulesRoot) {
    throw new Error('parseAppModulePath requires an appModulesRoot option.');
  }

  const relative = path.relative(appModulesRoot, filePath);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    return null;
  }

  const [appId, segment] = toPosix(relative).split('/');
  if (!appId) {
    return null;
  }

  return { appId, segment: segment ?? '' };
}

export function isPlatformModulePath(filePath, options) {
  const webSrcRoot = typeof options === 'string' ? options : options?.webSrcRoot;
  if (!webSrcRoot) {
    throw new Error('isPlatformModulePath requires a webSrcRoot option.');
  }

  const relative = path.relative(webSrcRoot, filePath);
  if (relative.startsWith('..') || path.isAbsolute(relative)) {
    return false;
  }

  return toPosix(relative).startsWith('platform/');
}

export function isAppModuleRootSegment(segment) {
  return !segment || segment === 'index';
}

export function resolveSpecifier(importer, specifier, options) {
  const { webSrcRoot } = options;

  if (specifier.startsWith('@/src/')) {
    return path.join(webSrcRoot, specifier.slice('@/src/'.length));
  }

  if (specifier.startsWith('./') || specifier.startsWith('../')) {
    return path.resolve(path.dirname(importer), specifier);
  }

  return null;
}

export function collectSpecifiers(source) {
  const specifiers = [];
  const staticPattern = /\b(?:import|export)\s+(?:type\s+)?(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]/g;
  const dynamicPattern = /\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)/g;

  for (const pattern of [staticPattern, dynamicPattern]) {
    let match;
    while ((match = pattern.exec(source)) !== null) {
      specifiers.push(match[1]);
    }
  }

  return specifiers;
}

export function walkSourceFiles(dir, options = {}) {
  const fsModule = options.fsModule ?? fs;
  const extensions = options.sourceExtensions ?? sourceExtensions;
  const skippedDirs = options.skippedDirectories ?? skippedDirectories;
  const entries = fsModule
    .readdirSync(dir, { withFileTypes: true })
    .toSorted((left, right) => left.name.localeCompare(right.name));
  const files = [];

  for (const entry of entries) {
    if (skippedDirs.has(entry.name)) {
      continue;
    }

    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkSourceFiles(fullPath, options));
    } else if (extensions.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }

  return files;
}

export function getSpecifierViolation(importer, specifier, options) {
  const { appModulesRoot } = options;
  const segments = options.internalSegments ?? internalSegments;
  const importerApp = parseAppModulePath(importer, { appModulesRoot });
  const isAppModuleRootAlias = appModuleRootAliasPattern.test(specifier);
  const isPublicAppModuleAlias = publicAppModuleAliasPattern.test(specifier);

  if (specifier.startsWith('@/src/components/views/')) {
    return {
      file: importer,
      specifier,
      reason: 'App-specific views must live inside app-modules/<appId>/views, not shared components/views.',
    };
  }

  if (specifier.startsWith('@/src/domains/')) {
    return {
      file: importer,
      specifier,
      reason: 'Legacy domains imports are closed. Use platform/* or app-modules/<appId> public/internal boundaries.',
    };
  }

  if (specifier.includes('components/views/PMSView')) {
    return {
      file: importer,
      specifier,
      reason: 'PMS views must live behind app-modules/pms public or relative module imports.',
    };
  }

  if (
    specifier.startsWith('@/src/app-modules/') &&
    !isPublicAppModuleAlias
  ) {
    return {
      file: importer,
      specifier,
      reason: 'Import app modules through their public module root or manifest boundary only.',
    };
  }

  if (
    isAppModuleRootAlias &&
    isPlatformModulePath(importer, options)
  ) {
    return {
      file: importer,
      specifier,
      reason: 'Platform modules must consume feature modules through shell adapters or app public-api, not app module roots.',
    };
  }

  const resolved = resolveSpecifier(importer, specifier, options);
  if (!resolved) {
    return null;
  }

  const targetApp = parseAppModulePath(resolved, { appModulesRoot });
  if (!targetApp) {
    return null;
  }

  if (
    !importerApp &&
    isAppModuleRootSegment(targetApp.segment) &&
    isPlatformModulePath(importer, options)
  ) {
    return {
      file: importer,
      specifier,
      reason: 'Platform modules must consume feature modules through shell adapters or app public-api, not app module roots.',
    };
  }

  if (importerApp && importerApp.appId !== targetApp.appId) {
    if (isPublicAppModuleAlias) {
      return null;
    }

    return {
      file: importer,
      specifier,
      reason: `Cross-app imports must go through the shell registry/public app boundary, not ${importerApp.appId} to ${targetApp.appId}.`,
    };
  }

  if (!importerApp && segments.has(targetApp.segment)) {
    return {
      file: importer,
      specifier,
      reason: `Outside app-modules cannot import ${targetApp.appId}/${targetApp.segment} internals.`,
    };
  }

  return null;
}

export function collectBoundaryViolations(files, options) {
  const readFile = options.readFile ?? ((file) => fs.readFileSync(file, 'utf8'));
  const violations = [];

  for (const file of files) {
    const source = readFile(file);

    for (const specifier of collectSpecifiers(source)) {
      const violation = getSpecifierViolation(file, specifier, options);
      if (violation) {
        violations.push(violation);
      }
    }
  }

  return violations;
}

export function runWebAppBoundaryCheck(repoRoot = process.cwd(), options = {}) {
  const paths = createBoundaryPaths(repoRoot);
  const files = options.files ?? walkSourceFiles(paths.webSrcRoot, options);
  const violations = collectBoundaryViolations(files, {
    ...options,
    ...paths,
  });

  return {
    ok: violations.length === 0,
    violations,
    ...paths,
  };
}

export function formatViolations(violations, repoRoot) {
  const lines = ['Web app boundary violations found:', ''];

  for (const violation of violations) {
    lines.push(`- ${path.relative(repoRoot, violation.file)} imports "${violation.specifier}"`);
    lines.push(`  ${violation.reason}`);
  }

  return lines.join('\n');
}

export function runCli(options = {}) {
  const cwd = options.cwd ?? process.cwd();
  const stdout = options.stdout ?? console.log;
  const stderr = options.stderr ?? console.error;
  const result = runWebAppBoundaryCheck(cwd, options);

  if (!result.ok) {
    stderr(formatViolations(result.violations, result.repoRoot));
    return 1;
  }

  stdout('Web app module boundaries OK');
  return 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = runCli();
}
