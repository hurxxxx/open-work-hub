import { MOCKUP_COLORS } from './mockup-theme';

type Coord = number | string;

interface MockupLineProps {
  x: Coord;
  y: Coord;
  w: Coord;
  color?: string;
}

const DEFAULT_LINE_COLOR = MOCKUP_COLORS.text;

export function MockupLine({
  x,
  y,
  w,
  color = DEFAULT_LINE_COLOR,
}: MockupLineProps) {
  return <rect x={x} y={y} width={w} height="1.6" rx="0.8" fill={color} />;
}
