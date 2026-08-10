export function getTaskDetailMutationErrorMessage(
  error: unknown,
  fallback: string,
): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export async function notifyTaskDetailUpdated(
  onUpdate?: () => void | Promise<void>,
): Promise<void> {
  await Promise.resolve(onUpdate?.());
}
