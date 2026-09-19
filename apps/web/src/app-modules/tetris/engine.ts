export const WIDTH = 10;
export const HEIGHT = 20;
export const KINDS = ['I', 'J', 'L', 'O', 'S', 'T', 'Z'] as const;
export type Kind = (typeof KINDS)[number];
export type Cell = Kind | null;
export type Matrix = readonly (readonly number[])[];
export const SHAPES: Record<Kind, Matrix> = {
  I: [
    [0, 0, 0, 0],
    [1, 1, 1, 1],
    [0, 0, 0, 0],
    [0, 0, 0, 0],
  ],
  J: [
    [1, 0, 0],
    [1, 1, 1],
    [0, 0, 0],
  ],
  L: [
    [0, 0, 1],
    [1, 1, 1],
    [0, 0, 0],
  ],
  O: [
    [1, 1],
    [1, 1],
  ],
  S: [
    [0, 1, 1],
    [1, 1, 0],
    [0, 0, 0],
  ],
  T: [
    [0, 1, 0],
    [1, 1, 1],
    [0, 0, 0],
  ],
  Z: [
    [1, 1, 0],
    [0, 1, 1],
    [0, 0, 0],
  ],
};
export interface Piece {
  kind: Kind;
  shape: Matrix;
  x: number;
  y: number;
}
export interface Game {
  board: Cell[][];
  active: Piece | null;
  queue: Kind[];
  hold: Kind | null;
  canHold: boolean;
  score: number;
  lines: number;
  level: number;
  status: 'ready' | 'playing' | 'paused' | 'over';
}
export type Action =
  | 'left'
  | 'right'
  | 'down'
  | 'tick'
  | 'clockwise'
  | 'counterclockwise'
  | 'drop'
  | 'hold'
  | 'pause'
  | 'resume';
export function emptyGame(): Game {
  return {
    board: Array.from({ length: HEIGHT }, () => Array<Cell>(WIDTH).fill(null)),
    active: null,
    queue: [],
    hold: null,
    canHold: true,
    score: 0,
    lines: 0,
    level: 1,
    status: 'ready',
  };
}
function bag(random: () => number): Kind[] {
  const result = [...KINDS];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}
function spawn(kind: Kind): Piece {
  return {
    kind,
    shape: SHAPES[kind],
    x: Math.floor((WIDTH - SHAPES[kind].length) / 2),
    y: 0,
  };
}
export function fits(board: Cell[][], piece: Piece): boolean {
  return piece.shape.every((row, y) =>
    row.every(
      (cell, x) =>
        !cell ||
        (piece.x + x >= 0 &&
          piece.x + x < WIDTH &&
          piece.y + y >= 0 &&
          piece.y + y < HEIGHT &&
          board[piece.y + y][piece.x + x] === null),
    ),
  );
}
function activate(game: Game, kind: Kind): Game {
  const active = spawn(kind);
  return {
    ...game,
    active,
    status: fits(game.board, active) ? 'playing' : 'over',
  };
}
function takeNext(game: Game, random: () => number): Game {
  const queue = [...game.queue];
  if (queue.length < 2) queue.push(...bag(random));
  const kind = queue.shift()!;
  return activate({ ...game, queue, canHold: true }, kind);
}
export function startGame(random: () => number = Math.random): Game {
  return takeNext(emptyGame(), random);
}
export function fallInterval(level: number): number {
  return Math.max(100, 1000 * 0.8 ** (level - 1));
}
function lock(game: Game, random: () => number): Game {
  if (!game.active) return game;
  const board = game.board.map((row) => [...row]);
  const piece = game.active;
  piece.shape.forEach((row, y) =>
    row.forEach((cell, x) => {
      if (cell) board[piece.y + y][piece.x + x] = piece.kind;
    }),
  );
  const remaining = board.filter((row) => row.some((cell) => cell === null));
  const cleared = HEIGHT - remaining.length;
  const lines = game.lines + cleared;
  return takeNext(
    {
      ...game,
      board: [
        ...Array.from({ length: cleared }, () => Array<Cell>(WIDTH).fill(null)),
        ...remaining,
      ],
      score: game.score + [0, 100, 300, 500, 800][cleared] * game.level,
      lines,
      level: 1 + Math.floor(lines / 10),
    },
    random,
  );
}
export function step(
  game: Game,
  action: Action,
  random: () => number = Math.random,
): Game {
  if (action === 'pause')
    return game.status === 'playing' ? { ...game, status: 'paused' } : game;
  if (action === 'resume')
    return game.status === 'paused' ? { ...game, status: 'playing' } : game;
  if (game.status !== 'playing' || !game.active) return game;
  const piece = game.active;
  if (action === 'hold') {
    if (!game.canHold) return game;
    const next = game.hold ? activate(game, game.hold) : takeNext(game, random);
    return { ...next, hold: piece.kind, canHold: false };
  }
  if (action === 'drop') {
    let active = piece;
    let distance = 0;
    while (fits(game.board, { ...active, y: active.y + 1 })) {
      active = { ...active, y: active.y + 1 };
      distance++;
    }
    return lock({ ...game, active, score: game.score + distance * 2 }, random);
  }
  if (action === 'clockwise' || action === 'counterclockwise') {
    const size = piece.shape.length;
    const shape = piece.shape.map((row, y) =>
      row.map((_, x) =>
        action === 'clockwise'
          ? piece.shape[size - 1 - x][y]
          : piece.shape[x][size - 1 - y],
      ),
    );
    for (const offset of [0, -1, 1, -2, 2]) {
      const active = { ...piece, shape, x: piece.x + offset };
      if (fits(game.board, active)) return { ...game, active };
    }
    return game;
  }
  const downward = action === 'down' || action === 'tick';
  const active = {
    ...piece,
    x: piece.x + (action === 'left' ? -1 : action === 'right' ? 1 : 0),
    y: piece.y + (downward ? 1 : 0),
  };
  if (fits(game.board, active))
    return { ...game, active, score: game.score + (action === 'down' ? 1 : 0) };
  return downward ? lock(game, random) : game;
}
export function visibleBoard(game: Game): Cell[][] {
  const board = game.board.map((row) => [...row]);
  if (game.active && game.status !== 'over') {
    const piece = game.active;
    piece.shape.forEach((row, y) =>
      row.forEach((cell, x) => {
        if (cell) board[piece.y + y][piece.x + x] = piece.kind;
      }),
    );
  }
  return board;
}
