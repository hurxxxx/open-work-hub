# Diagrams App

Draw.io runs as a separate container. API stores diagram XML and PNG previews.

## Env

- Local may use `OPEN_WORK_HUB_DRAWIO_BIND_HOST=0.0.0.0` and empty `OPEN_WORK_HUB_DRAWIO_SERVER_URL`.
- Public env sets HTTPS `OPEN_WORK_HUB_DRAWIO_SERVER_URL` on a separate origin.
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

- Do not proxy draw.io below main Hub origin.
- Rollback may keep draw.io container, but reactivation requires healthy container, TLS, diagram tables, and MinIO access.
