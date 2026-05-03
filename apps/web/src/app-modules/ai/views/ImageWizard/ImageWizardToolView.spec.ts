import { describe, expect, it } from 'vitest';

import {
  shouldReviewImageEditInstruction,
  shouldStartNewGenerationForTemplatePick,
} from './ImageWizardToolView';

describe('shouldReviewImageEditInstruction', () => {
  it('keeps information gathering in the agent path instead of keyword-routing to review', () => {
    expect(shouldReviewImageEditInstruction('삼성전자 2024년 2025년 실적 비교 수치 넣어줘')).toBe(false);
    expect(shouldReviewImageEditInstruction('최신 제품 스펙을 찾아서 카드에 반영해줘')).toBe(false);
    expect(shouldReviewImageEditInstruction('research current pricing and update the table')).toBe(false);
  });

  it('allows direct edits for concrete visual-only changes', () => {
    expect(shouldReviewImageEditInstruction('배경을 더 밝게 하고 오른쪽 카드만 강조해줘')).toBe(false);
    expect(shouldReviewImageEditInstruction('제목은 유지하고 로고를 제거해줘')).toBe(false);
  });
});

describe('shouldStartNewGenerationForTemplatePick', () => {
  it('forks template picks from approved generations', () => {
    expect(shouldStartNewGenerationForTemplatePick(null)).toBe(false);
    expect(shouldStartNewGenerationForTemplatePick({ brief_status: 'drafting' })).toBe(false);
    expect(shouldStartNewGenerationForTemplatePick({ brief_status: 'ready' })).toBe(false);
    expect(shouldStartNewGenerationForTemplatePick({ brief_status: 'approved' })).toBe(true);
  });
});
