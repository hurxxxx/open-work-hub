import type { ImageGeneration } from '../../api/image-wizard-api';

const AMBIGUOUS_EDIT_TERMS = [
  '\uC88B\uAC8C',
  '\uC608\uC058\uAC8C',
  '\uACE0\uAE09\uC2A4\uB7FD',
  '\uC790\uC5F0\uC2A4\uB7FD',
  '\uC138\uB828',
  '\uD604\uB300\uC801',
  '\uAC1C\uC120',
  '\uBA4B\uC9C0\uAC8C',
  '\uAE54\uB054\uD558\uAC8C',
  '\uC54C\uC544\uC11C',
];

const CONCRETE_EDIT_TERMS = [
  '\uBC30\uACBD',
  '\uC0C9',
  '\uD14D\uC2A4\uD2B8',
  '\uBB38\uAD6C',
  '\uC81C\uBAA9',
  '\uB85C\uACE0',
  '\uC81C\uAC70',
  '\uC0AD\uC81C',
  '\uCD94\uAC00',
  '\uBC1D',
  '\uC5B4\uB461',
  '\uAC15\uC870',
  '\uC67C\uCABD',
  '\uC624\uB978\uCABD',
  '\uC704',
  '\uC544\uB798',
  '\uD06C\uAC8C',
  '\uC791\uAC8C',
  '\uD45C\uC815',
];

const LARGE_EDIT_PATTERNS = [
  /\uC644\uC804\uD788/,
  /\uC804\uBD80/,
  /\uCC98\uC74C\uBD80\uD130/,
  /\uAC08\uC544\uC5CE/,
  /\uC0C8 \uC774\uBBF8\uC9C0\uCC98\uB7FC/,
  /\uC544\uC608/,
  /\uC804\uCCB4\s*(\uC2A4\uD0C0\uC77C|\uAD6C\uB3C4|\uB808\uC774\uC544\uC6C3|\uCEE8\uC149)/,
];

function includesAnyTerm(value: string, terms: readonly string[]): boolean {
  return terms.some((term) => value.includes(term));
}

function matchesAnyPattern(value: string, patterns: readonly RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(value));
}

function isAmbiguousImageEdit(value: string): boolean {
  return (
    includesAnyTerm(value, AMBIGUOUS_EDIT_TERMS) &&
    !includesAnyTerm(value, CONCRETE_EDIT_TERMS)
  );
}

export function shouldReviewImageEditInstruction(instruction: string): boolean {
  const normalized = instruction.trim().toLowerCase();
  if (!normalized) return false;
  return matchesAnyPattern(normalized, LARGE_EDIT_PATTERNS) || isAmbiguousImageEdit(normalized);
}

export function shouldStartNewGenerationForTemplatePick(
  row: Pick<ImageGeneration, 'brief_status'> | null,
): boolean {
  return row?.brief_status === 'approved';
}
