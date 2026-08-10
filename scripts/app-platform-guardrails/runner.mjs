import { checkAppPlatformGuardrails } from './engine.mjs';
import { createGitChangeSource } from './git-changes.mjs';
import { validateAppManifestContracts } from './manifest.mjs';
import {
  validateCodeownersProtectedSurface,
  validateGitlabCiGuardrailArtifact,
} from './ownership.mjs';
import { validateWindowsDevGuardrails } from './windows.mjs';
import { runWebAppBoundaryCheck } from '../check-web-app-boundaries.mjs';
import { validateWorkspaceKeywordSearchHarness } from './workspace-keyword-search.mjs';

export {
  collectGitChanges,
  createGitChangeSource,
  parseGitNameStatus,
  refExists,
  resolveBaseRef,
  runGit,
} from './git-changes.mjs';

export const DEFAULT_GUARDRAIL_VALIDATORS = Object.freeze([
  {
    code: 'app-manifest-contract',
    message: 'App manifest contract validation failed.',
    validate: ({ repoRoot }) => validateAppManifestContracts({ repoRoot }),
    formatError: (error) => `${error.manifestPath}: ${error.message}`,
  },
  {
    code: 'workspace-keyword-search-contract',
    message: 'Workspace keyword search ownership validation failed.',
    validate: ({ repoRoot }) =>
      validateWorkspaceKeywordSearchHarness({ repoRoot }),
    formatError: (error) => `${error.filePath}: ${error.message}`,
  },
  {
    code: 'windows-dev-guardrails',
    message: 'Windows administrator dev guardrail validation failed.',
    validate: ({ repoRoot }) => validateWindowsDevGuardrails({ repoRoot }),
    formatError: (error) => `${error.filePath}: ${error.message}`,
  },
  {
    code: 'protected-surface-ownership',
    message: 'Protected surface owner routing validation failed.',
    validate: ({ repoRoot }) =>
      validateCodeownersProtectedSurface({ repoRoot }),
    formatError: (error) => `${error.filePath}: ${error.message}`,
  },
  {
    code: 'guardrail-ci-artifact',
    message: 'Guardrail CI artifact validation failed.',
    validate: ({ repoRoot }) => validateGitlabCiGuardrailArtifact({ repoRoot }),
    formatError: (error) => `${error.filePath}: ${error.message}`,
  },
  {
    code: 'web-app-boundaries',
    message: 'Web app module boundary validation failed.',
    validate: ({ repoRoot }) => {
      const result = runWebAppBoundaryCheck(repoRoot);
      return {
        ok: result.ok,
        errors: result.violations,
      };
    },
    formatError: (error) =>
      `${error.file}: ${error.specifier}: ${error.reason}`,
  },
]);

function collectChanges(changeSource, context) {
  if (Array.isArray(changeSource)) {
    return changeSource;
  }
  if (typeof changeSource === 'function') {
    return changeSource(context);
  }
  if (changeSource && typeof changeSource.collect === 'function') {
    return changeSource.collect(context);
  }
  return createGitChangeSource(context).collect(context);
}

function defaultValidationErrorFormatter(error) {
  if (typeof error === 'string') {
    return error;
  }
  if (error?.filePath && error?.message) {
    return `${error.filePath}: ${error.message}`;
  }
  if (error?.manifestPath && error?.message) {
    return `${error.manifestPath}: ${error.message}`;
  }
  if (error?.message) {
    return error.message;
  }
  return JSON.stringify(error);
}

export function appendValidationFailure(result, validationResult, validator) {
  if (validationResult.ok) {
    return result;
  }
  const formatError = validator.formatError ?? defaultValidationErrorFormatter;
  return {
    ...result,
    ok: false,
    failures: [
      ...result.failures,
      {
        code: validator.code,
        message: validator.message,
        details: (validationResult.errors ?? []).map(formatError),
      },
    ],
  };
}

export function runGuardrailValidators(result, validators, context) {
  return validators.reduce((currentResult, validator) => {
    const validationResult = validator.validate(context);
    return appendValidationFailure(currentResult, validationResult, validator);
  }, result);
}

export function runGuardrailSuite({
  allowRepoWideRewrite,
  baseRef = null,
  changeSource,
  changes,
  env = process.env,
  guardrailOptions = {},
  lane,
  declaredLane,
  repoRoot = process.cwd(),
  validators = DEFAULT_GUARDRAIL_VALIDATORS,
} = {}) {
  const context = { baseRef, env, repoRoot };
  const collectedChanges = collectChanges(changes ?? changeSource, context);
  const selectedLane = declaredLane ?? lane;
  const engineOptions = { ...guardrailOptions, env };
  if (selectedLane !== undefined) {
    engineOptions.declaredLane = selectedLane;
  }
  if (allowRepoWideRewrite !== undefined) {
    engineOptions.allowRepoWideRewrite = allowRepoWideRewrite;
  }
  const result = checkAppPlatformGuardrails(collectedChanges, engineOptions);

  return runGuardrailValidators(result, validators, {
    ...context,
    changes: collectedChanges,
    guardrailResult: result,
  });
}
