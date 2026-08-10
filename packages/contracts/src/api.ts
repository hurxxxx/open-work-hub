import type { components, paths } from './openapi.generated.js';

export type ApiPath = keyof paths;
export type ApiSchema<Name extends keyof components['schemas']> = components['schemas'][Name];
export type ApiOperation<
  Path extends ApiPath,
  Method extends keyof paths[Path],
> = NonNullable<paths[Path][Method]>;

type JsonContent<Response> = Response extends {
  content: { 'application/json': infer Json };
}
  ? Json
  : never;

export type ApiJsonResponse<
  Path extends ApiPath,
  Method extends keyof paths[Path],
> = ApiOperation<Path, Method> extends { responses: infer Responses }
  ? 200 extends keyof Responses
    ? JsonContent<Responses[200]>
    : 201 extends keyof Responses
      ? JsonContent<Responses[201]>
      : 204 extends keyof Responses
        ? void
        : never
  : never;

export type ApiJsonRequestBody<
  Path extends ApiPath,
  Method extends keyof paths[Path],
> = ApiOperation<Path, Method> extends {
  requestBody: { content: { 'application/json': infer Body } };
}
  ? Body
  : never;
