const appModuleIds = [
  'home',
  'ai',
  'pms',
  'docs',
  'planner',
  'meeting',
  'learning',
  'settings',
];

const privateAppModuleEntry = (appId) =>
  `^apps/web/src/app-modules/${appId}/(?:api|lib|model|pages|routes|sidebar|ui|views)(?:[/.]|$)`;

module.exports = {
  forbidden: [
    {
      name: 'no-web-circular-dependencies',
      comment: 'Web source modules should not form dependency cycles.',
      severity: 'error',
      from: {
        path: '^apps/web/src',
      },
      to: {
        circular: true,
      },
    },
    ...appModuleIds.map((appId) => ({
      name: `no-${appId}-private-imports-outside-owner`,
      comment:
        'App module internals must stay behind the app module public API.',
      severity: 'error',
      from: {
        path: '^apps/web/src',
        pathNot: `^apps/web/src/app-modules/${appId}/`,
      },
      to: {
        path: privateAppModuleEntry(appId),
      },
    })),
  ],
  options: {
    doNotFollow: {
      path: 'node_modules',
    },
    enhancedResolveOptions: {
      extensions: ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.json'],
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'default'],
    },
    progress: {
      type: 'none',
    },
    tsConfig: {
      fileName: 'tsconfig.web-boundaries.json',
    },
  },
};
