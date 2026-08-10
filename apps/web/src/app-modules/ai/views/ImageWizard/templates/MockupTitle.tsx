import { MOCKUP_COLORS } from './mockup-theme';

type Coord = number | string;

interface MockupTitleProps {
  x: Coord;
  y: Coord;
  w: Coord;
  h?: Coord;
  color?: string;
}

const DEFAULT_TITLE_COLOR = MOCKUP_COLORS.textHeavy;

export function MockupTitle({
  x,
  y,
  w,
  h = 4,
  color = DEFAULT_TITLE_COLOR,
}: MockupTitleProps) {
  return <rect x={x} y={y} width={w} height={h} rx="1" fill={color} />;
}
