import { laneLabel } from './classifier.mjs';

export function formatGuardrailReport(result) {
  const lines = [];
  lines.push('[app-platform-guardrails]');
  lines.push(`  required lane: ${result.requiredLane ? laneLabel(result.requiredLane) : 'None'}`);
  lines.push(`  declared lane: ${result.declaredLane ? laneLabel(result.declaredLane) : 'not declared'}`);
  lines.push(`  changed files: ${result.changedFileCount}`);
  lines.push(`  deleted files: ${result.deletedFileCount}`);

  if (result.ok) {
    lines.push('  status: OK');
    return lines.join('\n');
  }

  lines.push('  status: FAILED');
  lines.push('');
  for (const failure of result.failures) {
    lines.push(`- ${failure.message}`);
    if (failure.nextAction) {
      lines.push(`  Next action: ${failure.nextAction}`);
    }
    if (failure.details) {
      for (const detail of failure.details) {
        lines.push(`  - ${detail}`);
      }
    }
    if (failure.hits) {
      for (const hit of failure.hits) {
        lines.push(`  - ${hit.path} (${hit.status})`);
        for (const surface of hit.surfaces) {
          lines.push(`    Surface: ${surface.label}`);
          lines.push(`    Required lane: ${laneLabel(surface.requiredLane)}`);
          lines.push(`    Next action: ${surface.nextAction}`);
        }
      }
    }
  }

  return lines.join('\n');
}

export function formatGuardrailOutput(result, { json = false } = {}) {
  return json ? JSON.stringify(result, null, 2) : formatGuardrailReport(result);
}
