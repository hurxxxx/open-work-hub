ARG NODE_IMAGE=node@sha256:78839ac448c23517f8eab2e8f7943d9b4f73979eb7f8bed2c73dbf72ff869e7b
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58
ARG POSTGRES_CLIENT_IMAGE=postgres@sha256:7bade6d532592ca8ce7ee32def7399dad2607c4ea5583839fc4352a095a11ea6

FROM ${NODE_IMAGE} AS node_toolchain

FROM node_toolchain AS validation_node_runtime

RUN npm install --global --force corepack@0.34.0 \
    && corepack enable \
    && corepack prepare pnpm@10.33.0 --activate

ARG NODE_DEPENDENCY_SHA256

WORKDIR /opt/open-work-hub/node-runtime

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/contracts/package.json packages/contracts/package.json
COPY packages/core-web/package.json packages/core-web/package.json
COPY packages/ui/package.json packages/ui/package.json

RUN test -n "${NODE_DEPENDENCY_SHA256}" \
    && actual_node_dependency_sha256="$( \
      { \
        sha256sum package.json | awk '{print $1}'; \
        sha256sum pnpm-lock.yaml | awk '{print $1}'; \
        sha256sum pnpm-workspace.yaml | awk '{print $1}'; \
        sha256sum packages/contracts/package.json | awk '{print $1}'; \
        sha256sum packages/core-web/package.json | awk '{print $1}'; \
        sha256sum packages/ui/package.json | awk '{print $1}'; \
      } | sha256sum | awk '{print $1}' \
    )" \
    && test "${actual_node_dependency_sha256}" = "${NODE_DEPENDENCY_SHA256}" \
    && pnpm install --frozen-lockfile --ignore-scripts \
    && printf '%s\n' "${NODE_DEPENDENCY_SHA256}" > dependency.sha256 \
    && pnpm exec nx --version \
    && pnpm exec openapi-typescript --version

FROM ${POSTGRES_CLIENT_IMAGE} AS postgres_client

FROM ${UV_IMAGE}

COPY --from=node_toolchain /usr/local/ /usr/local/
COPY --from=postgres_client /usr/lib/postgresql/17/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres_client /usr/lib/postgresql/17/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=postgres_client /usr/lib/postgresql/17/bin/psql /usr/local/bin/psql
COPY --from=postgres_client /usr/lib/x86_64-linux-gnu/libpq.so.5.18 /usr/local/lib/libpq.so.5.18

ENV LD_LIBRARY_PATH=/usr/local/lib

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      bash \
      build-essential \
      ca-certificates \
      curl \
      git \
      jq \
      libpq-dev \
      postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --force corepack@0.34.0 \
    && corepack enable \
    && corepack prepare pnpm@10.33.0 --activate \
    && node --version \
    && pnpm --version \
    && python --version \
    && jq --version \
    && uv --version \
    && pg_dump --version | grep -Eq '^pg_dump \(PostgreSQL\) 17\.' \
    && pg_restore --version | grep -Eq '^pg_restore \(PostgreSQL\) 17\.' \
    && psql --version | grep -Eq '^psql \(PostgreSQL\) 17\.'

ARG API_DEPENDENCY_SHA256

COPY apps/api/pyproject.toml apps/api/uv.lock /opt/open-work-hub/locks/api/

RUN test -n "${API_DEPENDENCY_SHA256}" \
    && actual_api_dependency_sha256="$( \
      { \
        sha256sum /opt/open-work-hub/locks/api/pyproject.toml | awk '{print $1}'; \
        sha256sum /opt/open-work-hub/locks/api/uv.lock | awk '{print $1}'; \
      } | sha256sum | awk '{print $1}' \
    )" \
    && test "${actual_api_dependency_sha256}" = "${API_DEPENDENCY_SHA256}" \
    && UV_COMPILE_BYTECODE=1 \
      UV_PROJECT_ENVIRONMENT=/opt/open-work-hub/venvs/api \
      uv sync \
        --directory /opt/open-work-hub/locks/api \
        --frozen \
        --python 3.12 \
        --group dev \
        --no-cache \
        --no-install-project \
    && printf '%s\n' "${API_DEPENDENCY_SHA256}" \
      > /opt/open-work-hub/locks/api/dependency.sha256 \
    && UV_OFFLINE=1 /opt/open-work-hub/venvs/api/bin/python -I -c \
      'import pytest, xdist; assert pytest.version_tuple[0] == 8' \
    && rm -rf /root/.cache/uv

ARG WORKER_DEPENDENCY_SHA256

COPY apps/worker/pyproject.toml apps/worker/uv.lock /opt/open-work-hub/locks/worker/

RUN test -n "${WORKER_DEPENDENCY_SHA256}" \
    && actual_worker_dependency_sha256="$( \
      { \
        sha256sum /opt/open-work-hub/locks/worker/pyproject.toml | awk '{print $1}'; \
        sha256sum /opt/open-work-hub/locks/worker/uv.lock | awk '{print $1}'; \
      } | sha256sum | awk '{print $1}' \
    )" \
    && test "${actual_worker_dependency_sha256}" = "${WORKER_DEPENDENCY_SHA256}" \
    && UV_COMPILE_BYTECODE=1 \
      UV_PROJECT_ENVIRONMENT=/opt/open-work-hub/venvs/worker \
      uv sync \
        --directory /opt/open-work-hub/locks/worker \
        --frozen \
        --python 3.12 \
        --group dev \
        --no-cache \
        --no-install-project \
    && printf '%s\n' "${WORKER_DEPENDENCY_SHA256}" \
      > /opt/open-work-hub/locks/worker/dependency.sha256 \
    && UV_OFFLINE=1 /opt/open-work-hub/venvs/worker/bin/python -I -c \
      'import pytest; assert pytest.version_tuple[0] == 8' \
    && rm -rf /root/.cache/uv

COPY --from=validation_node_runtime \
  /opt/open-work-hub/node-runtime \
  /opt/open-work-hub/node-runtime

ENV UV_LINK_MODE=copy
ENV OPEN_WORK_HUB_API_IMAGE_DEPENDENCY_FILE=/opt/open-work-hub/locks/api/dependency.sha256
ENV OPEN_WORK_HUB_API_IMAGE_VENV=/opt/open-work-hub/venvs/api
ENV OPEN_WORK_HUB_NODE_IMAGE_DEPENDENCY_FILE=/opt/open-work-hub/node-runtime/dependency.sha256
ENV OPEN_WORK_HUB_NODE_IMAGE_MODULES=/opt/open-work-hub/node-runtime/node_modules
ENV OPEN_WORK_HUB_WORKER_IMAGE_DEPENDENCY_FILE=/opt/open-work-hub/locks/worker/dependency.sha256
ENV OPEN_WORK_HUB_WORKER_IMAGE_VENV=/opt/open-work-hub/venvs/worker
WORKDIR /builds
