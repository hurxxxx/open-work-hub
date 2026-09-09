#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const GIB = 1024 ** 3;
const RETENTION_MS = 48 * 60 * 60 * 1000;
const CACHE_LABELS = [
  'io.open-work-hub.build-cache=true',
  'org.opencontainers.image.title=Open Work Hub',
];
const KEEP_TAGS = [
  'open-work-hub-app:prod',
  'open-work-hub-app:prod-previous',
  'open-work-hub-validation:node22-python312',
];
const RELEASE_TAG = /^open-work-hub-app:[0-9a-f]{12}$/;
const VALIDATION_TAG =
  /^open-work-hub-validation:(?:deps-[0-9a-f]{12}|(?:before-)?agents-[0-9a-f]{8}|redis64-impact-release)$/;

export function diskHeadroom(stats) {
  const available = stats.bavail * stats.bsize;
  const total = stats.blocks * stats.bsize;
  return {
    ok:
      Number.isFinite(available) &&
      total > 0 &&
      available >= 15 * GIB &&
      available / total >= 0.15,
    availableGiB: +(available / GIB).toFixed(1),
    usedPercent: +((1 - available / total) * 100).toFixed(1),
  };
}

export function requireDiskHeadroom(root = '/') {
  const result = diskHeadroom(fs.statfsSync(root));
  if (!result.ok)
    throw new Error(
      `Insufficient build/test disk headroom (${result.availableGiB} GiB free, ${result.usedPercent}% used); require >=15 GiB and >=15% free. Clean only verified project artifacts, not data volumes or disk-watermark guards.`,
    );
  return result;
}

// Only known generated image tags are candidates. Other repositories, manual
// tags, current/previous releases and ALL container references remain protected.
export function retirementPlan(images, containers, now = Date.now()) {
  const pinned = new Set(containers.map((container) => container.Image));
  for (const image of images) {
    if ((image.RepoTags ?? []).some((tag) => KEEP_TAGS.includes(tag)))
      pinned.add(image.Id);
  }
  const currentApp = images.find((image) =>
    (image.RepoTags ?? []).includes(KEEP_TAGS[0]),
  );
  const currentCi = images.find((image) =>
    (image.RepoTags ?? []).includes(KEEP_TAGS[2]),
  );
  return images
    .filter((image) => {
      const tags = image.RepoTags ?? [];
      const created = Date.parse(image.Created);
      if (
        pinned.has(image.Id) ||
        !tags.length ||
        !Number.isFinite(created) ||
        now - created < RETENTION_MS
      )
        return false;
      if (tags.every((tag) => RELEASE_TAG.test(tag))) {
        return (
          Boolean(currentApp) &&
          image.Config?.Labels?.['org.opencontainers.image.title'] ===
            'Open Work Hub'
        );
      }
      return (
        Boolean(currentCi) && tags.every((tag) => VALIDATION_TAG.test(tag))
      );
    })
    .map((image) => ({ id: image.Id, tags: image.RepoTags }));
}

function docker(args) {
  try {
    return execFileSync('docker', args, {
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch {
    throw new Error(
      'Docker storage inspection/operation failed; no force deletion attempted.',
    );
  }
}

function snapshot() {
  const ids = [
    ...new Set(
      docker(['image', 'ls', '-q', '--no-trunc'])
        .trim()
        .split('\n')
        .filter(Boolean),
    ),
  ];
  const containerIds = docker(['ps', '-aq', '--no-trunc'])
    .trim()
    .split('\n')
    .filter(Boolean);
  return {
    images: ids.length ? JSON.parse(docker(['image', 'inspect', ...ids])) : [],
    containers: containerIds.length
      ? JSON.parse(docker(['inspect', ...containerIds]))
      : [],
  };
}

export function cleanup({
  apply = false,
  inspect = snapshot,
  invoke = docker,
} = {}) {
  const state = inspect();
  const plan = retirementPlan(state.images, state.containers);
  console.log(
    JSON.stringify({
      mode: apply ? 'apply' : 'plan',
      retiredImages: plan,
      cachePolicy:
        'Only positively labeled project build-cache/app dangling images older than 48h; no volumes, containers, global prune or backup archives.',
    }),
  );
  if (!apply) return;
  for (const candidate of plan) {
    const fresh = inspect();
    const current = retirementPlan(fresh.images, fresh.containers).find(
      (image) => image.id === candidate.id,
    );
    if (
      !current ||
      JSON.stringify([...current.tags].sort()) !==
        JSON.stringify([...candidate.tags].sort())
    ) {
      throw new Error(
        'Image references changed during cleanup; stopped without force deletion.',
      );
    }
    // --no-prune avoids implicitly deleting uninspected parent images.
    invoke(['image', 'rm', '--no-prune', ...candidate.tags]);
    console.log(`[docker-storage] retired ${candidate.id}`);
  }
  // Docker owns dependency/reference tracking. This positive label and age
  // filter never selects current tagged images or other projects' caches.
  for (const label of CACHE_LABELS) {
    invoke([
      'image',
      'prune',
      '--force',
      '--filter',
      `label=${label}`,
      '--filter',
      'until=48h',
    ]);
  }
  console.log('[docker-storage] scoped dangling-cache retention completed.');
}

function localDockerRoot() {
  const root = docker(['info', '--format', '{{.DockerRootDir}}']).trim();
  const endpoint = docker([
    'context',
    'inspect',
    '--format',
    '{{.Endpoints.docker.Host}}',
  ]).trim();
  if (
    !endpoint.startsWith('unix://') ||
    process.env.DOCKER_HOST ||
    !root.startsWith('/')
  ) {
    throw new Error(
      'Host storage operations require the local Docker context; inspect remote storage at its owner.',
    );
  }
  return root;
}

export function main(args = process.argv.slice(2)) {
  if (args.length === 1 && args[0] === 'check') {
    console.log(JSON.stringify(requireDiskHeadroom(localDockerRoot())));
  } else if (
    args[0] === 'cleanup' &&
    (args.length === 1 || (args.length === 2 && args[1] === '--apply'))
  ) {
    localDockerRoot();
    cleanup({ apply: args[1] === '--apply' });
  } else if (args.length === 1 && args[0] === '--help') {
    console.log(
      'node scripts/docker-storage.mjs check\nnode scripts/docker-storage.mjs cleanup [--apply]\nDefault cleanup is read-only. Apply requires explicit project build-artifact cleanup or deployment scope. Never backs up images or deletes volumes.',
    );
  } else throw new Error('Use check or cleanup [--apply]; see --help.');
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    main();
  } catch (error) {
    console.error(`[docker-storage] ${error.message}`);
    process.exitCode = 1;
  }
}
