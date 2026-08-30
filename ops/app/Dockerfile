# syntax=docker/dockerfile:1.7

ARG NODE_IMAGE=node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579

FROM ${NODE_IMAGE} AS web-build

WORKDIR /opt/open-work-hub

RUN corepack enable \
  && corepack prepare pnpm@10.33.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml nx.json tsconfig.base.json ./
COPY packages/contracts/package.json packages/contracts/package.json
COPY packages/collab-codec-runtime/package.json packages/collab-codec-runtime/package.json
COPY packages/core-web/package.json packages/core-web/package.json
COPY packages/ui/package.json packages/ui/package.json
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm nx build web --skip-nx-cache
RUN pnpm --filter @open-work-hub/collab-codec-runtime deploy \
    --prod --legacy /opt/collab-codec-runtime

FROM ${PYTHON_IMAGE} AS python-build

COPY --from=ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823 /uv /usr/local/bin/uv

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/open-work-hub

COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md apps/api/
COPY apps/worker/pyproject.toml apps/worker/uv.lock apps/worker/README.md apps/worker/
RUN UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    uv sync --frozen --no-dev --no-install-project --directory apps/api \
  && UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    uv sync --frozen --no-dev --no-install-project --directory apps/worker

COPY apps/api/src apps/api/src
COPY apps/api/alembic apps/api/alembic
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/worker/src apps/worker/src
RUN UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    uv sync --frozen --no-dev --no-editable --directory apps/api \
  && UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    uv sync --frozen --no-dev --no-editable --directory apps/worker

FROM ${PYTHON_IMAGE} AS runtime

ARG OPEN_WORK_HUB_BUILD_REVISION=unmanaged

LABEL org.opencontainers.image.title="Open Work Hub" \
  org.opencontainers.image.revision="${OPEN_WORK_HUB_BUILD_REVISION}"

ENV OPEN_WORK_HUB_RUNTIME_REVISION="${OPEN_WORK_HUB_BUILD_REVISION}" \
  PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates libstdc++6 poppler-utils librsvg2-bin \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --gid 10001 open-work-hub \
  && useradd --uid 10001 --gid open-work-hub --create-home --home-dir /opt/open-work-hub open-work-hub

WORKDIR /opt/open-work-hub

COPY --from=python-build /opt/open-work-hub/apps/api/.venv apps/api/.venv
COPY --from=python-build /opt/open-work-hub/apps/worker/.venv apps/worker/.venv
COPY --chown=open-work-hub:open-work-hub apps/api/src apps/api/src
COPY --chown=open-work-hub:open-work-hub apps/api/alembic apps/api/alembic
COPY --chown=open-work-hub:open-work-hub apps/api/alembic.ini apps/api/alembic.ini
COPY --chown=open-work-hub:open-work-hub apps/worker/src apps/worker/src
COPY --chown=open-work-hub:open-work-hub pnpm-workspace.yaml pnpm-workspace.yaml
COPY --chown=open-work-hub:open-work-hub packages/contracts/open-work-hub-desktop-update-feed.manifest.json packages/contracts/open-work-hub-desktop-update-feed.manifest.json
COPY --chown=open-work-hub:open-work-hub scripts/blocknote-collab-codec.mjs scripts/blocknote-collab-codec.mjs
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
COPY --from=web-build --chown=open-work-hub:open-work-hub /opt/collab-codec-runtime/node_modules node_modules
COPY --from=web-build --chown=open-work-hub:open-work-hub /opt/open-work-hub/dist/apps/web dist/apps/web

RUN mkdir -p .runtime/opf-cache .runtime/recording-spool \
  && chown -R open-work-hub:open-work-hub .runtime

USER open-work-hub

CMD ["apps/api/.venv/bin/uvicorn", "open_work_hub_api.main:app", "--app-dir", "apps/api/src", "--host", "127.0.0.1", "--port", "14201"]
