import Ajv2020 from 'ajv/dist/2020.js';

function formatSchemaErrors(errors = []) {
  return errors
    .map((error) => `${error.instancePath || '/'} ${error.message}`)
    .join('\n');
}

export function validateAppContracts(source, schema) {
  const ajv = new Ajv2020({ allErrors: true, strict: true });
  const validate = ajv.compile(schema);
  if (!validate(source)) {
    throw new Error(
      `Invalid app contract schema:\n${formatSchemaErrors(validate.errors)}`,
    );
  }

  const appIds = new Set();
  const routeIds = new Set();
  const routeBases = new Set();
  for (const app of source.apps) {
    if (appIds.has(app.app_id))
      throw new Error(`Duplicate app id: ${app.app_id}`);
    if (routeBases.has(app.route_base))
      throw new Error(`Duplicate route base: ${app.route_base}`);
    if (app.route_base !== `/apps/${app.app_id}`) {
      throw new Error(`Route base must match app id: ${app.app_id}`);
    }
    if (
      app.availability_scope === 'platform' &&
      app.routes.some((route) => route.context_scope !== 'global')
    ) {
      throw new Error(`Platform app routes must be global: ${app.app_id}`);
    }
    if (
      app.launcher.placement === 'personal_tools' &&
      (app.availability_scope !== 'platform' ||
        app.execution_context_kind !== 'personal')
    ) {
      throw new Error(
        `Personal-tools app must be platform/personal: ${app.app_id}`,
      );
    }

    appIds.add(app.app_id);
    routeBases.add(app.route_base);
    const appRouteIds = new Set(app.routes.map((route) => route.route_id));
    if (!appRouteIds.has(app.entry_route_id)) {
      throw new Error(
        `Unknown entry route ${app.entry_route_id} for ${app.app_id}`,
      );
    }
    const entryRoute = app.routes.find(
      (route) => route.route_id === app.entry_route_id,
    );
    if (
      app.availability_scope === 'workspace' &&
      entryRoute.context_scope !== 'workspace'
    ) {
      throw new Error(
        `Workspace app entry route must be workspace-scoped: ${app.app_id}`,
      );
    }
    for (const route of app.routes) {
      if (routeIds.has(route.route_id))
        throw new Error(`Duplicate route id: ${route.route_id}`);
      if (!route.route_id.startsWith(`${app.app_id}.`)) {
        throw new Error(
          `Route id must be owned by ${app.app_id}: ${route.route_id}`,
        );
      }
      if (
        route.context_scope === 'global' &&
        route.suffix.startsWith('/workspaces')
      ) {
        throw new Error(
          `Global route uses reserved workspace prefix: ${route.route_id}`,
        );
      }
      if (
        app.availability_scope === 'workspace' &&
        route.context_scope === 'global' &&
        route.chrome !== 'shared'
      ) {
        throw new Error(
          `Workspace app global route must use shared chrome: ${route.route_id}`,
        );
      }
      routeIds.add(route.route_id);
    }
  }
}
