# Diagrams App

Draw.io runs as a separate container. API stores diagram XML and PNG previews.

## Env

- Local may use `OPEN_WORK_HUB_DRAWIO_BIND_HOST=0.0.0.0` and empty `OPEN_WORK_HUB_DRAWIO_SERVER_URL`.
- Public deployments set an absolute HTTPS `OPEN_WORK_HUB_DRAWIO_SERVER_URL` on a dedicated origin.
- `OPEN_WORK_HUB_DRAWIO_IMAGE_TAG` pins image version.
- `OPEN_WORK_HUB_DRAWIO_PORT` is host port.
- Do not commit real `.env`.

## Deploy

1. Configure draw.io DNS/TLS.
2. Set env and image tag.
3. Run `scripts/infra-stack.sh <environment> up`.
4. Check container health and HTTP response.
5. Smoke new diagram create/save in Web.

## Boundary

- Do not proxy draw.io below the main Hub origin outside local development. The current dev Nginx
  profile and browser fallback use `/drawio/` when no absolute URL is configured; because the
  iframe permits both scripts and same-origin behavior, that fallback is not a safe public
  deployment boundary.
- The iframe bridge accepts messages only from the exact resolved draw.io origin and window. Hub
  access tokens and storage credentials never enter the iframe.
- Rollback may keep draw.io container, but reactivation requires healthy container, TLS, diagram tables, and MinIO access.
