import Ajv2020 from 'ajv/dist/2020.js';

export function validateAppContracts(source, schema) {
  const validate = new Ajv2020({ allErrors: true, strict: true }).compile(
    schema,
  );
  if (!validate(source)) {
    throw new Error(
      `Invalid app contract schema:\n${(validate.errors ?? []).map((error) => `${error.instancePath || '/'} ${error.message}`).join('\n')}`,
    );
  }
  const appIds = new Set();
  const routeIds = new Set();
  const routePaths = new Set();
  for (const app of source.apps) {
    if (appIds.has(app.app_id))
      throw new Error(`Duplicate app id: ${app.app_id}`);
    appIds.add(app.app_id);
    if (app.route_base !== `/apps/${app.app_id}`)
      throw new Error(`Route base must match app id: ${app.app_id}`);
    if (
      app.launcher.placement === 'personal_tools' &&
      app.execution_context_kind !== 'personal'
    ) {
      throw new Error(
        `Personal-tools app must use personal execution: ${app.app_id}`,
      );
    }
    if (!app.routes.some((route) => route.route_id === app.entry_route_id)) {
      throw new Error(
        `Unknown entry route ${app.entry_route_id} for ${app.app_id}`,
      );
    }
    for (const route of app.routes) {
      if (routeIds.has(route.route_id))
        throw new Error(`Duplicate route id: ${route.route_id}`);
      if (!route.route_id.startsWith(`${app.app_id}.`))
        throw new Error(
          `Route id must be owned by ${app.app_id}: ${route.route_id}`,
        );
      const routePath = `${app.route_base}${route.suffix}`;
      if (routePaths.has(routePath))
        throw new Error(`Duplicate route path: ${routePath}`);
      if (route.suffix.startsWith('/workspaces'))
        throw new Error(
          `Product workspace routes are unsupported: ${route.route_id}`,
        );
      routeIds.add(route.route_id);
      routePaths.add(routePath);
    }
  }
}
