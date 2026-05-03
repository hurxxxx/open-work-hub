import { describe, expect, it } from 'vitest';

import { shouldReviewImageEditInstruction } from './ImageWizardToolView';

describe('shouldReviewImageEditInstruction', () => {
  it('requires a reviewed plan when an edit needs information gathering', () => {
    expect(shouldReviewImageEditInstruction('삼성전자 2024년 2025년 실적 비교 수치 넣어줘')).toBe(true);
    expect(shouldReviewImageEditInstruction('최신 제품 스펙을 찾아서 카드에 반영해줘')).toBe(true);
    expect(shouldReviewImageEditInstruction('research current pricing and update the table')).toBe(true);
  });

  it('allows direct edits for concrete visual-only changes', () => {
    expect(shouldReviewImageEditInstruction('배경을 더 밝게 하고 오른쪽 카드만 강조해줘')).toBe(false);
    expect(shouldReviewImageEditInstruction('제목은 유지하고 로고를 제거해줘')).toBe(false);
  });
});
