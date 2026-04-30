#!/usr/bin/env node

import fs from 'node:fs';
import path from 'node:path';

const repoRoot = process.cwd();
const webSrcRoot = path.join(repoRoot, 'apps/web/src');
const appModulesRoot = path.join(webSrcRoot, 'app-modules');
const internalSegments = new Set(['api', 'lib', 'model', 'pages', 'routes', 'sidebar', 'ui', 'views']);
const publicAppModuleAliasPattern = /^@\/src\/app-modules\/[^/]+(?:\/manifest|\/public-api)?$/;
const sourceExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs']);

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (entry.name === 'node_modules' || entry.name === 'dist') {
      continue;
    }
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walk(fullPath));
    } else if (sourceExtensions.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }
  return files;
}

function toPosix(filePath) {
  return filePath.split(path.sep).join('/');
}

function parseAppModulePath(filePath) {
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

function resolveSpecifier(importer, specifier) {
  if (specifier.startsWith('@/src/')) {
    return path.join(webSrcRoot, specifier.slice('@/src/'.length));
  }
  if (specifier.startsWith('./') || specifier.startsWith('../')) {
    return path.resolve(path.dirname(importer), specifier);
  }
  return null;
}

function collectSpecifiers(source) {
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

const violations = [];

for (const file of walk(webSrcRoot)) {
  const source = fs.readFileSync(file, 'utf8');
  const importerApp = parseAppModulePath(file);

  for (const specifier of collectSpecifiers(source)) {
    const isPublicAppModuleAlias = publicAppModuleAliasPattern.test(specifier);

    if (specifier.startsWith('@/src/components/views/')) {
      violations.push({
        file,
        specifier,
        reason: 'App-specific views must live inside app-modules/<appId>/views, not shared components/views.',
      });
      continue;
    }

    if (specifier.startsWith('@/src/domains/')) {
      violations.push({
        file,
        specifier,
        reason: 'Legacy domains imports are closed. Use platform/* or app-modules/<appId> public/internal boundaries.',
      });
      continue;
    }

    if (specifier.includes('components/views/PMSView')) {
      violations.push({
        file,
        specifier,
        reason: 'PMS views must live behind app-modules/pms public or relative module imports.',
      });
      continue;
    }

    if (
      specifier.startsWith('@/src/app-modules/') &&
      !isPublicAppModuleAlias
    ) {
      violations.push({
        file,
        specifier,
        reason: 'Import app modules through their public module root or manifest boundary only.',
      });
      continue;
    }

    const resolved = resolveSpecifier(file, specifier);
    if (!resolved) {
      continue;
    }

    const targetApp = parseAppModulePath(resolved);
    if (!targetApp) {
      continue;
    }

    if (importerApp && importerApp.appId !== targetApp.appId) {
      if (isPublicAppModuleAlias) {
        continue;
      }
      violations.push({
        file,
        specifier,
        reason: `Cross-app imports must go through the shell registry/public app boundary, not ${importerApp.appId} to ${targetApp.appId}.`,
      });
      continue;
    }

    if (!importerApp && internalSegments.has(targetApp.segment)) {
      violations.push({
        file,
        specifier,
        reason: `Outside app-modules cannot import ${targetApp.appId}/${targetApp.segment} internals.`,
      });
    }
  }
}

if (violations.length > 0) {
  console.error('Web app boundary violations found:\n');
  for (const violation of violations) {
    console.error(`- ${path.relative(repoRoot, violation.file)} imports "${violation.specifier}"`);
    console.error(`  ${violation.reason}`);
  }
  process.exit(1);
}

console.log('Web app module boundaries OK');
