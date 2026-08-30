#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { isIP } from 'node:net';
import { pathToFileURL } from 'node:url';

const REQUEST_TIMEOUT_MS = 10_000;

export function normalizePublicBaseUrl(rawValue) {
  if (!rawValue?.trim()) {
    throw new Error('OPEN_WORK_HUB_UAT_BASE_URL is required');
  }

  let url;
  try {
    url = new URL(rawValue);
  } catch {
    throw new Error('OPEN_WORK_HUB_UAT_BASE_URL must be a valid URL');
  }

  const hostname = url.hostname.toLowerCase().replace(/\.$/, '');
  if (url.protocol !== 'https:') {
    throw new Error('OPEN_WORK_HUB_UAT_BASE_URL must use https');
  }
  if (
    !hostname.includes('.') ||
    hostname === 'localhost' ||
    hostname.endsWith('.localhost') ||
    hostname.endsWith('.local') ||
    isIP(hostname) !== 0
  ) {
    throw new Error('OPEN_WORK_HUB_UAT_BASE_URL must use a public domain name');
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(
      'OPEN_WORK_HUB_UAT_BASE_URL must not contain credentials, query, or fragment',
    );
  }
  if (url.pathname !== '/' && url.pathname !== '') {
    throw new Error(
      'OPEN_WORK_HUB_UAT_BASE_URL must be an origin without a path',
    );
  }

  return new URL(`${url.origin}/`);
}

export function assertRuntimeStatus(output) {
  for (const service of ['web', 'api', 'worker']) {
    if (!new RegExp(`^${service}\\s+running\\b`, 'm').test(output)) {
      throw new Error(`development ${service} service is not running`);
    }
  }
}

export function assertWorkerPing(output) {
  if (/no nodes replied/i.test(output) || !/\bpong\b/i.test(output)) {
    throw new Error('development worker did not answer the Celery ping');
  }
}

export async function assertJsonEndpoint(label, url, expectedStatus) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('application/json')) {
    throw new Error(`${label} did not return JSON`);
  }
  const body = await response.json();
  if (body?.status !== expectedStatus) {
    throw new Error(`${label} reported status ${String(body?.status)}`);
  }
}

export async function assertLoginPage(label, url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
  const contentType = response.headers.get('content-type') ?? '';
  const body = await response.text();
  if (
    !contentType.toLowerCase().includes('text/html') ||
    !/(?:<!doctype html|<html)/i.test(body) ||
    !/<div[^>]+id=["']root["']/i.test(body)
  ) {
    throw new Error(`${label} did not return the rendered web shell`);
  }
}

export async function assertOkEndpoint(label, url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
}

async function fetchWithTimeout(url) {
  try {
    return await fetch(url, {
      redirect: 'follow',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`request failed: ${detail}`);
  }
}

function localPort(name, fallback) {
  const value = process.env[name] ?? fallback;
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65_535) {
    throw new Error(`${name} must be a valid TCP port`);
  }
  return value;
}

export async function runPreflight() {
  const publicBaseUrl = normalizePublicBaseUrl(
    process.env.OPEN_WORK_HUB_UAT_BASE_URL,
  );
  const apiPort = localPort('OPEN_WORK_HUB_API_DEV_PORT', '8001');
  const webPort = localPort('OPEN_WORK_HUB_WEB_DEV_PORT', '4200');
  const localApi = new URL(`http://127.0.0.1:${apiPort}/`);
  const localWeb = new URL(`http://127.0.0.1:${webPort}/`);
  const objectStorageEndpoint = new URL(
    process.env.OPEN_WORK_HUB_MINIO_ENDPOINT ?? 'http://127.0.0.1:59010',
  );
  if (objectStorageEndpoint.username || objectStorageEndpoint.password) {
    throw new Error(
      'OPEN_WORK_HUB_MINIO_ENDPOINT must not contain credentials',
    );
  }

  const status = execFileSync('./dev.sh', ['--with-worker', '--status'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  assertRuntimeStatus(status);

  let workerPing;
  try {
    workerPing = execFileSync(
      'uv',
      [
        'run',
        '--python',
        '3.12',
        'celery',
        '-A',
        'open_work_hub_worker.celery_app:celery_app',
        'inspect',
        'ping',
        '--timeout',
        '5',
      ],
      {
        cwd: new URL('../apps/worker/', import.meta.url),
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
        timeout: 15_000,
      },
    );
  } catch {
    throw new Error('development worker did not answer the Celery ping');
  }
  assertWorkerPing(workerPing);

  const checks = [
    ['local health', new URL('/healthz', localApi), 'ok'],
    ['local readiness', new URL('/readyz', localApi), 'ok'],
    ['public health', new URL('/healthz', publicBaseUrl), 'ok'],
    ['public readiness', new URL('/readyz', publicBaseUrl), 'ok'],
  ];
  for (const [label, url, expectedStatus] of checks) {
    await assertJsonEndpoint(label, url, expectedStatus);
  }
  await assertOkEndpoint(
    'object storage health',
    new URL('/minio/health/live', objectStorageEndpoint),
  );
  await assertLoginPage('local login', new URL('/login', localWeb));
  await assertLoginPage('public login', new URL('/login', publicBaseUrl));

  process.stdout.write(
    `UAT preflight passed for ${publicBaseUrl.origin}: web, api, worker ping, object storage, health, readiness, and the login HTML shell are available.\n`,
  );
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  runPreflight().catch((error) => {
    const detail = error instanceof Error ? error.message : String(error);
    process.stderr.write(`UAT preflight failed: ${detail}\n`);
    process.exitCode = 1;
  });
}
