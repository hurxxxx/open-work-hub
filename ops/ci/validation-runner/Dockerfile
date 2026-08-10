ARG NODE_IMAGE=node@sha256:78839ac448c23517f8eab2e8f7943d9b4f73979eb7f8bed2c73dbf72ff869e7b
ARG UV_IMAGE=ghcr.io/astral-sh/uv@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58

FROM ${NODE_IMAGE} AS node_toolchain

FROM node_toolchain AS validation_node_runtime

RUN npm install --global --force corepack@0.34.0 \
    && corepack enable \
    && corepack prepare pnpm@10.33.0 --activate

ARG NODE_DEPENDENCY_SHA256

WORKDIR /opt/open-alm/node-runtime

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
    && pnpm install \
      --frozen-lockfile \
      --ignore-scripts \
    && printf '%s\n' "${NODE_DEPENDENCY_SHA256}" \
      > dependency.sha256 \
    && node --input-type=module -e \
      "await import('@blocknote/core'); await import('@blocknote/react'); await import('yjs')" \
    && pnpm exec nx --version \
    && pnpm exec openapi-typescript --version

FROM ${UV_IMAGE}

COPY --from=node_toolchain /usr/local/ /usr/local/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
      bash \
      build-essential \
      ca-certificates \
      curl \
      git \
      jq \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --show-error --silent \
      --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && printf '%s  %s\n' \
      '0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76' \
      '/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc' \
      | sha256sum --check --strict - \
    && printf '%s\n' \
      'deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main' \
      > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
      libpq-dev \
      postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

RUN uv pip install --system --no-cache PyYAML==6.0.3 \
    && npm install --global --force corepack@0.34.0 \
    && corepack enable \
    && corepack prepare pnpm@10.33.0 --activate \
    && node --version \
    && pnpm --version \
    && python --version \
    && python -I -c 'import yaml; assert yaml.__version__ == "6.0.3"' \
    && jq --version \
    && pg_dump --version | grep -E '^pg_dump \(PostgreSQL\) 18\.' \
    && uv --version

ARG API_DEPENDENCY_SHA256

COPY apps/api/pyproject.toml apps/api/uv.lock /opt/open-alm/locks/api/

RUN test -n "${API_DEPENDENCY_SHA256}" \
    && actual_api_dependency_sha256="$( \
      { \
        sha256sum /opt/open-alm/locks/api/pyproject.toml | awk '{print $1}'; \
        sha256sum /opt/open-alm/locks/api/uv.lock | awk '{print $1}'; \
      } | sha256sum | awk '{print $1}' \
    )" \
    && test "${actual_api_dependency_sha256}" = "${API_DEPENDENCY_SHA256}" \
    && UV_COMPILE_BYTECODE=1 \
      UV_PROJECT_ENVIRONMENT=/opt/open-alm/venvs/api \
      uv sync \
        --directory /opt/open-alm/locks/api \
        --frozen \
        --python 3.12 \
        --group dev \
        --no-cache \
        --no-install-project \
    && printf '%s\n' "${API_DEPENDENCY_SHA256}" \
      > /opt/open-alm/locks/api/dependency.sha256 \
    && UV_OFFLINE=1 /opt/open-alm/venvs/api/bin/python -I -c \
      'import pytest, xdist; assert pytest.version_tuple[0] == 8' \
    && rm -rf /root/.cache/uv

ARG WORKER_DEPENDENCY_SHA256

COPY apps/worker/pyproject.toml apps/worker/uv.lock /opt/open-alm/locks/worker/

RUN test -n "${WORKER_DEPENDENCY_SHA256}" \
    && actual_worker_dependency_sha256="$( \
      { \
        sha256sum /opt/open-alm/locks/worker/pyproject.toml | awk '{print $1}'; \
        sha256sum /opt/open-alm/locks/worker/uv.lock | awk '{print $1}'; \
      } | sha256sum | awk '{print $1}' \
    )" \
    && test "${actual_worker_dependency_sha256}" = "${WORKER_DEPENDENCY_SHA256}" \
    && UV_COMPILE_BYTECODE=1 \
      UV_PROJECT_ENVIRONMENT=/opt/open-alm/venvs/worker \
      uv sync \
        --directory /opt/open-alm/locks/worker \
        --frozen \
        --python 3.12 \
        --group dev \
        --no-cache \
        --no-install-project \
    && printf '%s\n' "${WORKER_DEPENDENCY_SHA256}" \
      > /opt/open-alm/locks/worker/dependency.sha256 \
    && UV_OFFLINE=1 /opt/open-alm/venvs/worker/bin/python -I -c \
      'import pytest; assert pytest.version_tuple[0] == 8' \
    && rm -rf /root/.cache/uv

COPY --from=validation_node_runtime \
  /opt/open-alm/node-runtime \
  /opt/open-alm/node-runtime

ARG NODE_DEPENDENCY_SHA256

LABEL ai.do.validation.api-dependency-sha256="${API_DEPENDENCY_SHA256}"
LABEL ai.do.validation.node-dependency-sha256="${NODE_DEPENDENCY_SHA256}"
LABEL ai.do.validation.worker-dependency-sha256="${WORKER_DEPENDENCY_SHA256}"

ENV UV_LINK_MODE=copy
ENV OPEN_ALM_API_IMAGE_DEPENDENCY_FILE=/opt/open-alm/locks/api/dependency.sha256
ENV OPEN_ALM_API_IMAGE_VENV=/opt/open-alm/venvs/api
ENV OPEN_ALM_API_IMAGE_NODE_DEPENDENCY_FILE=/opt/open-alm/node-runtime/dependency.sha256
ENV OPEN_ALM_API_IMAGE_NODE_MODULES=/opt/open-alm/node-runtime/node_modules
ENV OPEN_ALM_NODE_IMAGE_DEPENDENCY_FILE=/opt/open-alm/node-runtime/dependency.sha256
ENV OPEN_ALM_NODE_IMAGE_MODULES=/opt/open-alm/node-runtime/node_modules
ENV OPEN_ALM_WORKER_IMAGE_DEPENDENCY_FILE=/opt/open-alm/locks/worker/dependency.sha256
ENV OPEN_ALM_WORKER_IMAGE_VENV=/opt/open-alm/venvs/worker
WORKDIR /builds
