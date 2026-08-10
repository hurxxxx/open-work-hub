import type { ContextRef, ContextRefKind } from '../../../api/image-wizard-api';

export type Step2ContextModal = ContextRefKind | null;

export interface Step2ContextBucketProjection {
  excludeIds: string[];
  refs: ContextRef[];
}

export interface Step2ContextProjection {
  docs: Step2ContextBucketProjection;
  meetings: Step2ContextBucketProjection;
  tasks: Step2ContextBucketProjection;
}

export interface ContextRefSource {
  id: string;
  title: string;
}

export function buildStep2ContextProjection(
  contextRefs: readonly ContextRef[],
): Step2ContextProjection {
  const meetings = filterContextRefsByKind(contextRefs, 'meeting');
  const tasks = filterContextRefsByKind(contextRefs, 'task');
  const docs = filterContextRefsByKind(contextRefs, 'doc');
  return {
    meetings: buildBucketProjection(meetings),
    tasks: buildBucketProjection(tasks),
    docs: buildBucketProjection(docs),
  };
}

export function attachContextRef(
  contextRefs: ContextRef[],
  next: ContextRef,
): ContextRef[] {
  if (contextRefs.some((ref) => isSameContextRef(ref, next))) return contextRefs;
  return [...contextRefs, next];
}

export function detachContextRef(
  contextRefs: readonly ContextRef[],
  kind: ContextRefKind,
  id: string,
): ContextRef[] {
  return contextRefs.filter((ref) => !(ref.kind === kind && ref.id === id));
}

export function buildPickedContextRef(
  kind: ContextRefKind,
  source: ContextRefSource,
): ContextRef {
  return {
    kind,
    id: source.id,
    snapshot: { title: source.title },
  };
}

export function getContextRefKey(ref: ContextRef): string {
  return `${ref.kind}:${ref.id}`;
}

export function getContextRefLabel(ref: ContextRef): string {
  return ref.snapshot?.title || ref.id;
}

function filterContextRefsByKind(
  contextRefs: readonly ContextRef[],
  kind: ContextRefKind,
): ContextRef[] {
  return contextRefs.filter((ref) => ref.kind === kind);
}

function buildBucketProjection(refs: ContextRef[]): Step2ContextBucketProjection {
  return {
    refs,
    excludeIds: refs.map((ref) => ref.id),
  };
}

function isSameContextRef(left: ContextRef, right: ContextRef): boolean {
  return left.kind === right.kind && left.id === right.id;
}
