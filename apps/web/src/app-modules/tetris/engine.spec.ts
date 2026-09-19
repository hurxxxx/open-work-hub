import { describe, expect, it } from 'vitest';
import {
  emptyGame,
  fallInterval,
  fits,
  HEIGHT,
  KINDS,
  SHAPES,
  startGame,
  step,
  visibleBoard,
  type Game,
  type Kind,
} from './engine';
const random = () => 0.5;
function piece(kind: Kind = 'O', x = 4, y = 0): Game {
  return { ...startGame(random), active: { kind, shape: SHAPES[kind], x, y } };
}
describe('tetris rules', () => {
  it('supplies each kind once per bag and always has a preview', () => {
    let game = startGame(random);
    const seen: Kind[] = [];
    for (let i = 0; i < 14; i++) {
      seen.push(game.active!.kind);
      expect(game.queue.length).toBeGreaterThan(0);
      game = step({ ...game, board: emptyGame().board }, 'drop', random);
    }
    expect(new Set(seen.slice(0, 7))).toEqual(new Set(KINDS));
    expect(new Set(seen.slice(7))).toEqual(new Set(KINDS));
  });
  it('blocks walls, floor and occupied cells without mutating its input', () => {
    const game = piece('O', 0, 18);
    expect(step(game, 'left')).toBe(game);
    expect(fits(game.board, { ...game.active!, y: 19 })).toBe(false);
    game.board[18][2] = 'T';
    expect(step(game, 'right')).toBe(game);
    const locked = step(game, 'tick', random);
    expect(locked.board[19][0]).toBe('O');
    expect(game.board[19][0]).toBeNull();
    expect(locked.score).toBe(0);
  });
  it('rotates both ways and uses horizontal wall kicks', () => {
    const game = piece('T');
    expect(step(step(game, 'clockwise'), 'counterclockwise').active).toEqual(
      game.active,
    );
    const vertical = step(piece('I'), 'clockwise');
    vertical.active!.x = -2;
    expect(fits(vertical.board, vertical.active!)).toBe(true);
    const rotated = step(vertical, 'counterclockwise');
    expect(rotated.active!.x).toBe(0);
    expect(rotated.active!.shape).toEqual(SHAPES.I);
  });
  it('rejects blocked rotations and never kicks upward from the floor', () => {
    const floor = piece('T', 4, 18);
    expect(step(floor, 'clockwise')).toBe(floor);
    const blocked = piece('T', 4, 5);
    blocked.board[7].fill('J');
    expect(step(blocked, 'clockwise')).toBe(blocked);
  });
  it.each([
    [1, 100],
    [2, 300],
    [3, 500],
    [4, 800],
  ])('clears %i lines simultaneously for %i points', (count, score) => {
    const game = piece('I');
    game.active = {
      kind: 'I',
      shape: [[1], [1], [1], [1]],
      x: 0,
      y: HEIGHT - 4,
    };
    for (let y = HEIGHT - count; y < HEIGHT; y++)
      game.board[y] = [null, ...Array<Kind>(9).fill('J')];
    const result = step(game, 'tick', random);
    expect(result.lines).toBe(count);
    expect(result.score).toBe(score);
    expect(result.board).toHaveLength(HEIGHT);
    expect(result.board.every((row) => row.some((cell) => cell === null))).toBe(
      true,
    );
  });
  it('scores at the current level and speeds up after ten lines with a speed floor', () => {
    const game = piece('I');
    game.active = { kind: 'I', shape: [[1], [1], [1], [1]], x: 0, y: 16 };
    game.board[19] = [null, ...Array<Kind>(9).fill('J')];
    game.lines = 19;
    game.level = 2;
    const result = step(game, 'tick', random);
    expect(result.score).toBe(200);
    expect(result.level).toBe(3);
    expect(fallInterval(1)).toBe(1000);
    expect(fallInterval(2)).toBe(800);
    expect(fallInterval(100)).toBe(100);
  });
  it('scores only actual soft and hard drop distance', () => {
    const game = piece();
    const down = step(game, 'down');
    expect(down.score).toBe(1);
    expect(step(down, 'drop', random).score).toBe(35);
    expect(step(piece('O', 4, 18), 'down', random).score).toBe(0);
  });
  it('holds only once before locking and resets the swapped piece orientation', () => {
    const game = piece('T');
    const held = step(step(game, 'clockwise'), 'hold', random);
    expect(held.hold).toBe('T');
    expect(step(held, 'hold')).toBe(held);
    const locked = step(held, 'drop', random);
    expect(locked.canHold).toBe(true);
    const swapped = step(locked, 'hold');
    expect(swapped.active!.shape).toEqual(SHAPES.T);
    expect(swapped.active!.y).toBe(0);
    expect(swapped.canHold).toBe(false);
  });
  it('ends when the next piece or a held piece cannot spawn', () => {
    const game = piece('O', 0, 18);
    game.queue = ['O', 'T'];
    game.hold = 'O';
    game.board[0][4] = 'J';
    expect(step(game, 'tick', random).status).toBe('over');
    expect(step(game, 'hold', random).status).toBe('over');
  });
  it('freezes paused and ended games, resumes explicitly and resets everything', () => {
    const game = step(piece(), 'pause');
    for (const action of ['tick', 'drop', 'hold', 'left'] as const)
      expect(step(game, action)).toBe(game);
    expect(step(game, 'resume').status).toBe('playing');
    const ended: Game = { ...game, status: 'over' };
    expect(step(ended, 'resume')).toBe(ended);
    const fresh = startGame(random);
    expect(fresh).toMatchObject({
      score: 0,
      lines: 0,
      level: 1,
      hold: null,
      canHold: true,
      status: 'playing',
    });
    expect(fresh.board.flat().every((cell) => cell === null)).toBe(true);
    expect(visibleBoard(fresh).flat().filter(Boolean)).toHaveLength(4);
    expect(fresh.board.flat().filter(Boolean)).toHaveLength(0);
  });
});
