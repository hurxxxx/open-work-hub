import type { ReactNode } from 'react';

import { MOCKUP_COLORS } from './mockup-theme';

interface MockupCardProps {
  children: ReactNode;
  bg?: string;
}

export function MockupCard({
  children,
  bg = MOCKUP_COLORS.cardBg,
}: MockupCardProps) {
  return (
    <svg viewBox="0 0 160 100" preserveAspectRatio="xMidYMid meet" aria-hidden>
      <rect x="0" y="0" width="160" height="100" fill={bg} />
      {children}
    </svg>
  );
}
