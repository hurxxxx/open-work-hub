import fs from 'node:fs';
import path from 'node:path';

import {
  parseManifestContractSource,
  validateManifestContract,
} from './manifest-contract-parser.mjs';

function pushManifestError(errors, manifestPath, message) {
  errors.push({ manifestPath, message });
}

export function validateManifestContractSource({
  appId,
  source,
  manifestPath = `apps/web/src/app-modules/${appId}/manifest.ts`,
  repoRoot = process.cwd(),
  pathExists = (relativePath) =>
    fs.existsSync(path.join(repoRoot, relativePath)),
} = {}) {
  const parsed = parseManifestContractSource(source);
  return [
    ...parsed.diagnostics.map((diagnostic) => ({
      manifestPath,
      message: diagnostic.message,
    })),
    ...validateManifestContract(parsed.contract, {
      appId,
      manifestPath,
      pathExists,
    }),
  ];
}

export function validateAppManifestContracts({
  repoRoot = process.cwd(),
} = {}) {
  const result = readAppManifestContracts({ repoRoot });
  return { ok: result.ok, errors: result.errors };
}

export function readAppManifestContracts({ repoRoot = process.cwd() } = {}) {
  const appModulesRoot = path.join(repoRoot, 'apps/web/src/app-modules');
  const errors = [];
  const manifests = [];
  if (!fs.existsSync(appModulesRoot)) {
    return {
      ok: false,
      manifests,
      errors: [
        {
          manifestPath: 'apps/web/src/app-modules',
          message: 'app modules root does not exist.',
        },
      ],
    };
  }

  const appIds = fs
    .readdirSync(appModulesRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();

  for (const appId of appIds) {
    const manifestPath = `apps/web/src/app-modules/${appId}/manifest.ts`;
    const absolutePath = path.join(repoRoot, manifestPath);
    if (!fs.existsSync(absolutePath)) {
      pushManifestError(
        errors,
        manifestPath,
        'manifest.ts is required for every app module.',
      );
      continue;
    }
    const source = fs.readFileSync(absolutePath, 'utf8');
    const parsed = parseManifestContractSource(source);
    const validationErrors = [
      ...parsed.diagnostics.map((diagnostic) => ({
        manifestPath,
        message: diagnostic.message,
      })),
      ...validateManifestContract(parsed.contract, {
        appId,
        manifestPath,
        pathExists: (relativePath) =>
          fs.existsSync(path.join(repoRoot, relativePath)),
      }),
    ];
    errors.push(...validationErrors);
    const contract = parsed.contract.contract;
    manifests.push({
      appId,
      manifestPath,
      apiDomain:
        contract?.apiDomain?.kind === 'string'
          ? contract.apiDomain.value
          : null,
      appLocalTests: Array.isArray(contract?.appLocalTests?.values)
        ? [...contract.appLocalTests.values]
        : null,
      workspaceApiPrefixes: Array.isArray(
        contract?.workspaceApiPrefixes?.values,
      )
        ? [...contract.workspaceApiPrefixes.values]
        : [],
      valid: validationErrors.length === 0,
    });
  }

  return { ok: errors.length === 0, manifests, errors };
}
