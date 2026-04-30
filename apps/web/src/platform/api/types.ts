import type { components, paths } from './openapi.generated';

export type ApiPath = keyof paths;
export type ApiSchema<Name extends keyof components['schemas']> = components['schemas'][Name];
