import { buildAppHref } from '@open-work-hub/contracts/app-routes';

export function buildBentoHubPath(workspaceSlug: string): string {
  return buildAppHref({ routeId: 'bento.root', workspaceSlug });
}

export function buildBentoPresentationPath(
  workspaceSlug: string,
  documentId: string,
): string {
  return buildAppHref({
    routeId: 'bento.presentation',
    workspaceSlug,
    pathParams: { documentId },
  });
}
