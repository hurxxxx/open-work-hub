import {
  classifyPath,
  isAppTestPath,
  laneCanCover,
  lanesFromMergeRequestLabels,
  laneLabel,
  normalizeLane,
  repoWideRewriteApprovalFromMergeRequestLabels,
} from './classifier.mjs';
import { dedupeChanges } from './git-changes.mjs';
import { migrationRiskForChange } from './migrations.mjs';
import {
  DEFAULT_LIMITS,
  LANES,
  LANE_RANK,
  PROTECTED_SURFACES,
} from './policy.mjs';

export { dedupeChanges } from './git-changes.mjs';

function affectedPaths(change) {
  return [change.path, change.previousPath].filter(Boolean);
}

export function isLaneOptionalPath(filePath) {
  if (
    /^(?:README\.md|docs\/(?:apps|domains|product|reference|final|archive)\/.*\.md|docs\/README\.md)$/.test(
      filePath,
    )
  ) {
    return true;
  }
  if (
    /^(?:apps\/web\/src\/platform\/i18n\/(?:resources|locales)\.ts|apps\/api\/src\/ai_do_api\/core\/i18n_catalog\.py)$/.test(
      filePath,
    )
  ) {
    return true;
  }
  if (
    /^(?:\.env\.example|scripts\/(?:check-env-contract\.py|check-runtime-separation\.py|tests\/test_env_contract\.py|tests\/test_runtime_separation\.py))$/.test(
      filePath,
    )
  ) {
    return true;
  }
  if (
    /^(?:agents\.md|\.gitlab-ci\.yml|\.gitlab\/merge_request_templates\/.*|ops\/ci\/.*|scripts\/(?:codex-review-ci\.sh|install-codex-review-runner\.sh|install-ci-light-validation-runner\.sh|install-ci-validation-runner\.sh|configure-ci-validation-env\.sh|promote-ci-control-plane\.sh|rollback-ci-control-plane\.sh|ci\/.*|app-platform-guardrails\/.*|check-app-platform-guardrails(?:\.test)?\.mjs|tests\/test_check_codex_review_ci\.py)|docs\/agents\/(?:local-codex-review|vibe-coding-harness)\.md|\.agents\/skills\/.*)$/.test(
      filePath,
    )
  ) {
    return true;
  }
  return (
    /^apps\/web\/src\/app-modules\/[^/]+\/.*\.(?:ts|tsx)$/.test(filePath) &&
    !/\/(?:manifest|public-api|routes|index)\.(?:ts|tsx)$/.test(filePath)
  );
}

function inferRequiredLane(classifiedChanges) {
  if (classifiedChanges.length === 0) {
    return null;
  }
  return classifiedChanges.reduce((current, change) => {
    if (!current) {
      return change.classification.lane;
    }
    return LANE_RANK[change.classification.lane] > LANE_RANK[current]
      ? change.classification.lane
      : current;
  }, null);
}

function mergeRequestLaneFor(requiredLane) {
  if (requiredLane === null) {
    return null;
  }
  if (requiredLane === LANES.PROTOTYPE || requiredLane === LANES.APP_SANDBOX) {
    return LANES.APP_SANDBOX;
  }
  if (requiredLane === LANES.HARNESS_AND_POLICY) {
    return LANES.HARNESS_AND_POLICY;
  }
  return LANES.CORE_PLATFORM;
}

export function checkAppPlatformGuardrails(rawChanges, options = {}) {
  const changes = dedupeChanges(rawChanges);
  const env = options.env ?? process.env;
  const mergeRequestLabels =
    options.mergeRequestLabels ?? env.CI_MERGE_REQUEST_LABELS ?? '';
  const mergeRequestLaneDeclarations =
    lanesFromMergeRequestLabels(mergeRequestLabels);
  const declaredLaneFromLabel = mergeRequestLaneDeclarations[0] ?? null;
  const isReleasePromotion =
    (env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
      Boolean(env.CI_MERGE_REQUEST_IID)) &&
    env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME === 'dev' &&
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME === 'main';
  const targetsDevMergeRequest =
    (env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
      Boolean(env.CI_MERGE_REQUEST_IID)) &&
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME === 'dev';
  const requireMergeRequestLane =
    options.requireMergeRequestLane ??
    (targetsDevMergeRequest &&
      changes.some((change) =>
        affectedPaths(change).some((filePath) => !isLaneOptionalPath(filePath)),
      ));
  const rawDeclaredLane =
    (requireMergeRequestLane
      ? declaredLaneFromLabel
      : (options.declaredLane ??
        env.AI_DO_CHANGE_LANE ??
        declaredLaneFromLabel)) ?? null;
  const declaredLane = normalizeLane(rawDeclaredLane);
  const rewriteApprovalFromLabel =
    repoWideRewriteApprovalFromMergeRequestLabels(mergeRequestLabels);
  const allowRepoWideRewrite =
    options.allowRepoWideRewrite === true ||
    env.AI_DO_ALLOW_REPO_WIDE_REWRITE === '1' ||
    (rewriteApprovalFromLabel &&
      (declaredLane === LANES.CORE_PLATFORM ||
        declaredLane === LANES.HARNESS_AND_POLICY));
  const maxDeletedFiles =
    options.maxDeletedFiles ?? DEFAULT_LIMITS.maxDeletedFiles;
  const maxChangedFiles =
    options.maxChangedFiles ?? DEFAULT_LIMITS.maxChangedFiles;
  const maxTopLevelDirectories =
    options.maxTopLevelDirectories ?? DEFAULT_LIMITS.maxTopLevelDirectories;

  const classifiedChanges = changes.map((change) => {
    const pathClassifications = affectedPaths(change).map((filePath) => ({
      filePath,
      ...classifyPath(filePath),
    }));
    const classification = pathClassifications.reduce((current, candidate) => {
      if (!current) {
        return candidate;
      }
      return LANE_RANK[candidate.lane] > LANE_RANK[current.lane]
        ? candidate
        : current;
    }, null);
    return {
      ...change,
      classification,
      pathClassifications,
    };
  });

  const classifiedRequiredLane = inferRequiredLane(classifiedChanges);
  const migrationRisks = changes
    .map((change) => migrationRiskForChange(change, options))
    .filter(Boolean);
  const requiredLane = migrationRisks.reduce(
    (current, risk) =>
      !current || LANE_RANK[risk.requiredLane] > LANE_RANK[current]
        ? risk.requiredLane
        : current,
    classifiedRequiredLane,
  );
  const expectedMergeRequestLane = mergeRequestLaneFor(requiredLane);
  const failures = [];
  const protectedHits = classifiedChanges.filter((change) =>
    change.pathClassifications.some(
      (classification) => classification.protectedSurface,
    ),
  );
  const hasAppSandboxSurface = classifiedChanges.some((change) =>
    change.pathClassifications.some(
      (classification) =>
        classification.lane === LANES.APP_SANDBOX &&
        !isAppTestPath(classification.filePath),
    ),
  );
  const hasHarnessPolicySurface = classifiedChanges.some((change) =>
    change.pathClassifications.some(
      (classification) => classification.lane === LANES.HARNESS_AND_POLICY,
    ),
  );

  if (!isReleasePromotion && hasAppSandboxSurface && hasHarnessPolicySurface) {
    failures.push({
      code: 'mixed-app-harness-policy',
      message:
        'App delivery and harness/policy changes must not share a merge request.',
      nextAction:
        'Split the app implementation from CI, agent rules, checkers, guardrails, CODEOWNERS, and policy changes.',
    });
  }

  if (requireMergeRequestLane && mergeRequestLaneDeclarations.length === 0) {
    failures.push({
      code: 'missing-lane',
      message:
        'Feature merge requests targeting dev must declare exactly one lane label.',
      nextAction:
        'Add exactly one of lane::app-sandbox, lane::core-platform, or lane::harness-and-policy.',
    });
  }

  if (requireMergeRequestLane && mergeRequestLaneDeclarations.length > 1) {
    failures.push({
      code: 'multiple-lanes',
      message: `Feature merge requests must declare exactly one lane label; found ${mergeRequestLaneDeclarations.length}.`,
      details: mergeRequestLaneDeclarations,
      nextAction: 'Keep only the single lane that covers the complete diff.',
    });
  }

  if (declaredLane === null && rawDeclaredLane) {
    failures.push({
      code: 'unknown-lane',
      message: `Unknown lane declaration: ${rawDeclaredLane}`,
    });
  }

  if (
    requireMergeRequestLane &&
    mergeRequestLaneDeclarations.length === 1 &&
    declaredLane !== null &&
    expectedMergeRequestLane !== null &&
    declaredLane !== expectedMergeRequestLane
  ) {
    failures.push({
      code: 'lane-mismatch',
      message: `${laneLabel(declaredLane)} is not the exact lane for ${laneLabel(requiredLane)} changes.`,
      nextAction: `Use exactly lane::${expectedMergeRequestLane}, or split the diff.`,
    });
  } else if (
    !isReleasePromotion &&
    !requireMergeRequestLane &&
    !laneCanCover({ declaredLane, requiredLane })
  ) {
    failures.push({
      code: 'lane-mismatch',
      message: `${laneLabel(declaredLane)} cannot cover ${laneLabel(requiredLane)} changes.`,
      nextAction: `Use the ${laneLabel(requiredLane)} lane or split this change.`,
    });
  }

  if (declaredLane === LANES.APP_SANDBOX) {
    const appSandboxProtectedHits = protectedHits.filter((change) =>
      change.pathClassifications.some(
        (classification) => classification.protectedSurface,
      ),
    );
    if (appSandboxProtectedHits.length > 0) {
      failures.push({
        code: 'protected-surface',
        message:
          'App Sandbox changes touched protected surface. Split the app-local work or route through the required lane.',
        hits: appSandboxProtectedHits.map((change) => ({
          path: change.path,
          status: change.status,
          surfaces: change.pathClassifications
            .filter((classification) => classification.protectedSurface)
            .map((classification) => {
              const details =
                PROTECTED_SURFACES[classification.protectedSurface];
              return {
                surface: classification.protectedSurface,
                label: details.label,
                requiredLane: details.requiredLane,
                nextAction: details.nextAction,
              };
            }),
        })),
      });
    }
  }

  const deletedFiles = changes.filter((change) =>
    change.status.startsWith('D'),
  );
  const uniqueCurrentPaths = new Set(changes.map((change) => change.path));
  const topLevelDirectories = new Set(
    [...uniqueCurrentPaths].map(
      (filePath) => filePath.split('/')[0] || filePath,
    ),
  );

  if (!allowRepoWideRewrite && deletedFiles.length >= maxDeletedFiles) {
    failures.push({
      code: 'mass-delete',
      message: `This change deletes ${deletedFiles.length} files, which exceeds the guardrail threshold of ${maxDeletedFiles}.`,
      nextAction:
        'Split the deletion into a reviewed cleanup lane, or set AI_DO_ALLOW_REPO_WIDE_REWRITE=1 only for an explicitly approved maintenance change.',
    });
  }

  if (
    !allowRepoWideRewrite &&
    uniqueCurrentPaths.size >= maxChangedFiles &&
    topLevelDirectories.size >= maxTopLevelDirectories
  ) {
    failures.push({
      code: 'repo-wide-rewrite',
      message: `This change touches ${uniqueCurrentPaths.size} files across ${topLevelDirectories.size} top-level areas.`,
      nextAction:
        'Reduce the change to an app-local slice or route it as an explicitly approved repo-wide maintenance change.',
    });
  }

  const uncoveredMigrationRisks = migrationRisks.filter(
    (risk) =>
      !isReleasePromotion &&
      (!declaredLane ||
        !laneCanCover({ declaredLane, requiredLane: risk.requiredLane })),
  );
  if (uncoveredMigrationRisks.length > 0) {
    failures.push({
      code: 'migration-escalation',
      message: 'Risky migration changes require the Core Platform lane.',
      nextAction:
        'Declare AI_DO_CHANGE_LANE=core-platform, or split the migration away from ordinary app work.',
      details: uncoveredMigrationRisks.map(
        (risk) => `${risk.path}: ${risk.reason} ${risk.nextAction}`,
      ),
    });
  }

  return {
    ok: failures.length === 0,
    declaredLane,
    mergeRequestLaneDeclarations,
    expectedMergeRequestLane,
    laneDeclarationSource:
      options.declaredLane != null
        ? 'option'
        : env.AI_DO_CHANGE_LANE
          ? 'AI_DO_CHANGE_LANE'
          : declaredLaneFromLabel
            ? 'CI_MERGE_REQUEST_LABELS'
            : null,
    requiredLane,
    changedFileCount: uniqueCurrentPaths.size,
    deletedFileCount: deletedFiles.length,
    topLevelDirectoryCount: topLevelDirectories.size,
    classifiedChanges,
    failures,
  };
}
