#!/usr/bin/env node

import { pathToFileURL } from 'node:url';

import {
  assertProductionAppEnv,
  readEnvFile,
} from './prod-app-config.mjs';
import { assertLoginPage } from './live-uat-preflight.mjs';

const REQUEST_TIMEOUT_MS = 15_000;

async function fetchResponse(label, url, headers = undefined) {
  let response;
  try {
    response = await fetch(url, {
      headers,
      redirect: 'follow',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`${label} request failed: ${detail}`);
  }
  return response;
}

async function fetchJson(label, url, headers = undefined) {
  const response = await fetchResponse(label, url, headers);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('application/json')) {
    throw new Error(`${label} did not return JSON`);
  }
  return response.json();
}

export async function assertDeploymentHealth(
  label,
  url,
  expectedRevision,
  headers = undefined,
) {
  const body = await fetchJson(label, url, headers);
  if (body?.status !== 'ok') {
    throw new Error(`${label} reported status ${String(body?.status)}`);
  }
  if (body?.environment !== 'production') {
    throw new Error(`${label} is not running the production environment`);
  }
  if (expectedRevision && body?.runtime_revision !== expectedRevision) {
    throw new Error(`${label} is serving a different runtime revision`);
  }
}

export async function assertDeploymentReadiness(
  label,
  url,
  expectedRevision,
) {
  const body = await fetchJson(label, url);
  if (body?.status !== 'ok') {
    throw new Error(`${label} reported status ${String(body?.status)}`);
  }
  if (body?.environment !== 'production') {
    throw new Error(`${label} is not running the production environment`);
  }
  if (body?.runtime_revision !== expectedRevision) {
    throw new Error(`${label} is serving a different runtime revision`);
  }
}

export async function assertBootstrapJson(label, url) {
  const body = await fetchJson(label, url);
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error(`${label} returned an invalid JSON object`);
  }
}

export async function assertEdgeHostRouting({
  edgeListenPort,
  edgeProdHost,
  expectedRevision,
}) {
  const edgeBaseUrl = new URL(`http://127.0.0.1:${edgeListenPort}/`);
  await assertDeploymentHealth(
    'edge production-host health',
    new URL('/healthz', edgeBaseUrl),
    expectedRevision,
    { Host: edgeProdHost },
  );
  const unknownHostResponse = await fetchResponse(
    'edge unknown-host rejection',
    new URL('/healthz', edgeBaseUrl),
    { Host: 'unconfigured.invalid' },
  );
  if (unknownHostResponse.status !== 421) {
    throw new Error(
      `edge accepted an unknown host with HTTP ${unknownHostResponse.status}`,
    );
  }
}

export async function runProductionSmoke({
  appPort,
  edgeListenPort,
  edgeProdHost,
  publicBaseUrl,
  expectedRevision,
}) {
  await assertEdgeHostRouting({
    edgeListenPort,
    edgeProdHost,
    expectedRevision,
  });
  const localBaseUrl = new URL(`http://127.0.0.1:${appPort}/`);
  for (const [label, baseUrl] of [
    ['local', localBaseUrl],
    ['public', publicBaseUrl],
  ]) {
    await assertDeploymentHealth(
      `${label} health`,
      new URL('/healthz', baseUrl),
      expectedRevision,
    );
    await assertDeploymentReadiness(
      `${label} readiness`,
      new URL('/readyz', baseUrl),
      expectedRevision,
    );
    await assertBootstrapJson(
      `${label} bootstrap`,
      new URL('/api/v1/auth/bootstrap-status', baseUrl),
    );
    await assertLoginPage(`${label} login`, new URL('/login', baseUrl));
  }
}

async function runCli() {
  const envPath = process.argv[2] ?? '.env';
  const config = assertProductionAppEnv(readEnvFile(envPath));
  const expectedRevision = (
    process.env.OPEN_WORK_HUB_EXPECTED_REVISION ?? ''
  ).trim();
  if (!expectedRevision) {
    throw new Error('OPEN_WORK_HUB_EXPECTED_REVISION is required');
  }
  await runProductionSmoke({ ...config, expectedRevision });
  process.stdout.write(
    'Production app smoke passed: edge host isolation, local and public health, readiness, revision, bootstrap, and login shell are available.\n',
  );
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  runCli().catch((error) => {
    const detail = error instanceof Error ? error.message : String(error);
    process.stderr.write(`Production app smoke failed: ${detail}\n`);
    process.exitCode = 1;
  });
}
