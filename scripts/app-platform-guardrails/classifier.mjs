import {
  APP_TEST_PATH_PATTERNS,
  CLASSIFICATION_SURFACE_ORDER,
  CORE_API_DOMAINS,
  LANES,
  LANE_LABELS,
  PROTECTED_SURFACES,
  WINDOWS_DEV_PATH_PATTERNS,
} from './policy.mjs';

function matchesAny(filePath, patterns = []) {
  return patterns.some((pattern) => pattern.test(filePath));
}

export function normalizePath(filePath) {
  return filePath.replace(/\\/g, '/').replace(/^\.\//, '');
}

export function isAppTestPath(rawPath) {
  return matchesAny(normalizePath(rawPath), APP_TEST_PATH_PATTERNS);
}

export function apiDomainForPath(filePath) {
  const match = /^apps\/api\/src\/ai_do_api\/domains\/([^/]+)(?:\/|$)/.exec(
    filePath,
  );
  return match?.[1] ?? null;
}

function appModuleForPath(filePath) {
  const match = /^apps\/web\/src\/app-modules\/([^/]+)(?:\/|$)/.exec(filePath);
  return match?.[1] ?? null;
}

function surfaceClassification(surfaceId) {
  const surface = PROTECTED_SURFACES[surfaceId];
  return {
    lane: surface.requiredLane,
    protectedSurface: surfaceId,
    reason: surface.reason ?? surface.label,
  };
}

export function classifyPath(rawPath) {
  const filePath = normalizePath(rawPath);

  if (matchesAny(filePath, PROTECTED_SURFACES['harness-policy'].pathPatterns)) {
    return surfaceClassification('harness-policy');
  }

  if (matchesAny(filePath, WINDOWS_DEV_PATH_PATTERNS)) {
    return {
      lane: LANES.WINDOWS_ADMIN_DEV_ENV,
      protectedSurface: null,
      reason: 'dedicated Windows administrator development surface',
    };
  }

  for (const surfaceId of CLASSIFICATION_SURFACE_ORDER) {
    if (surfaceId === 'harness-policy') {
      continue;
    }
    const surface = PROTECTED_SURFACES[surfaceId];
    if (matchesAny(filePath, surface.pathPatterns)) {
      return surfaceClassification(surfaceId);
    }
  }

  const apiDomain = apiDomainForPath(filePath);
  if (apiDomain) {
    if (CORE_API_DOMAINS.has(apiDomain)) {
      return {
        lane: LANES.CORE_PLATFORM,
        protectedSurface: 'api-core',
        reason: `API core domain: ${apiDomain}`,
      };
    }
    return {
      lane: LANES.APP_SANDBOX,
      protectedSurface: null,
      reason: `app-local API domain: ${apiDomain}`,
    };
  }

  const appModule = appModuleForPath(filePath);
  if (appModule) {
    return {
      lane: LANES.APP_SANDBOX,
      protectedSurface: null,
      reason: `app-local web module: ${appModule}`,
    };
  }

  if (
    /^apps\/worker\/src\/ai_do_worker\/tasks\/apps\/[a-z0-9_-]+\//.test(
      filePath,
    )
  ) {
    return {
      lane: LANES.APP_SANDBOX,
      protectedSurface: null,
      reason: 'scaffolded app-owned worker task module',
    };
  }

  if (/^apps\/api\/src\/ai_do_api\/core\//.test(filePath)) {
    return {
      lane: LANES.CORE_PLATFORM,
      protectedSurface: 'api-core',
      reason: 'API core module',
    };
  }

  if (/^apps\/api\/alembic\/versions\//.test(filePath)) {
    return {
      lane: LANES.APP_SANDBOX,
      protectedSurface: null,
      reason: 'app-owned migration candidate',
    };
  }

  if (
    /^apps\/api\/alembic\//.test(filePath) ||
    /^apps\/api\/alembic\.ini$/.test(filePath)
  ) {
    return {
      lane: LANES.CORE_PLATFORM,
      protectedSurface: 'api-core',
      reason: 'API migration harness',
    };
  }

  if (isAppTestPath(filePath)) {
    return {
      lane: LANES.APP_SANDBOX,
      protectedSurface: null,
      reason: 'app-local test or fixture candidate',
    };
  }

  if (
    /^learning\//.test(filePath) ||
    /^docs\//.test(filePath) ||
    /^README\.md$/.test(filePath)
  ) {
    return {
      lane: LANES.PROTOTYPE,
      protectedSurface: null,
      reason: 'documentation or learning material',
    };
  }

  return {
    lane: LANES.CORE_PLATFORM,
    protectedSurface: 'core-platform',
    reason: 'unclassified repository surface defaults to Core Platform review',
  };
}

export function laneLabel(lane) {
  return LANE_LABELS[lane] ?? lane;
}

export function normalizeLane(rawLane) {
  if (!rawLane) {
    return null;
  }
  const normalized = rawLane
    .trim()
    .toLowerCase()
    .replace(/[_\s]+/g, '-');
  const aliases = new Map([
    ['prototype', LANES.PROTOTYPE],
    ['app', LANES.APP_SANDBOX],
    ['app-sandbox', LANES.APP_SANDBOX],
    ['sandbox', LANES.APP_SANDBOX],
    ['shared', LANES.SHARED_CAPABILITY],
    ['shared-capability', LANES.SHARED_CAPABILITY],
    ['core', LANES.CORE_PLATFORM],
    ['core-platform', LANES.CORE_PLATFORM],
    ['harness', LANES.HARNESS_AND_POLICY],
    ['policy', LANES.HARNESS_AND_POLICY],
    ['harness-and-policy', LANES.HARNESS_AND_POLICY],
    ['windows', LANES.WINDOWS_ADMIN_DEV_ENV],
    ['windows-admin', LANES.WINDOWS_ADMIN_DEV_ENV],
    ['windows-admin-dev-env', LANES.WINDOWS_ADMIN_DEV_ENV],
  ]);
  return aliases.get(normalized) ?? null;
}

export function lanesFromMergeRequestLabels(rawLabels) {
  if (!rawLabels) {
    return [];
  }

  const lanes = [];
  for (const rawLabel of rawLabels.split(',')) {
    const label = rawLabel.trim();
    const match = /^(?:lane|change-lane)\s*(?:::|:|=|\/)\s*(.+)$/i.exec(label);
    if (match) {
      lanes.push(match[1].trim());
    }
  }

  return lanes;
}

export function laneFromMergeRequestLabels(rawLabels) {
  return lanesFromMergeRequestLabels(rawLabels)[0] ?? null;
}

export function repoWideRewriteApprovalFromMergeRequestLabels(rawLabels) {
  if (!rawLabels) {
    return false;
  }

  for (const rawLabel of rawLabels.split(',')) {
    const label = rawLabel.trim();
    if (/^allow-repo-wide-rewrite$/i.test(label)) {
      return true;
    }
    const match =
      /^(?:repo-wide|repo-wide-rewrite)\s*(?:::|:|=|\/)\s*(.+)$/i.exec(label);
    if (
      match &&
      /^(?:approved|allowed|allow|true|yes)$/i.test(match[1].trim())
    ) {
      return true;
    }
  }

  return false;
}

export function laneCanCover({ declaredLane, requiredLane }) {
  if (!declaredLane || !requiredLane) {
    return true;
  }
  if (declaredLane === requiredLane) {
    return true;
  }
  if (requiredLane === LANES.PROTOTYPE) {
    return true;
  }
  if (requiredLane === LANES.APP_SANDBOX) {
    return declaredLane !== LANES.PROTOTYPE;
  }
  if (requiredLane === LANES.SHARED_CAPABILITY) {
    return (
      declaredLane === LANES.CORE_PLATFORM ||
      declaredLane === LANES.HARNESS_AND_POLICY
    );
  }
  if (requiredLane === LANES.WINDOWS_ADMIN_DEV_ENV) {
    return declaredLane === LANES.CORE_PLATFORM;
  }
  if (requiredLane === LANES.CORE_PLATFORM) {
    return declaredLane === LANES.HARNESS_AND_POLICY;
  }
  return false;
}
