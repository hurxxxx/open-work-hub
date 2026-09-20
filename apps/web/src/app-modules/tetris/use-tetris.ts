import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import {
  emptyGame,
  fallInterval,
  startGame,
  step,
  type Action,
} from './engine';

const ACTIONS: Record<string, Action> = {
  ArrowLeft: 'left',
  ArrowRight: 'right',
  ArrowDown: 'down',
  ArrowUp: 'clockwise',
  KeyX: 'clockwise',
  KeyZ: 'counterclockwise',
  Space: 'drop',
  KeyC: 'hold',
};
export function useTetris() {
  const [game, setGame] = useState(emptyGame);
  const [round, setRound] = useState(0);
  const boardRef = useRef<HTMLDivElement>(null);
  const pause = useCallback(
    () => setGame((current) => step(current, 'pause')),
    [],
  );
  useEffect(() => {
    if (game.status !== 'playing') return;
    const timer = window.setInterval(
      () => setGame((current) => step(current, 'tick')),
      fallInterval(game.level),
    );
    return () => window.clearInterval(timer);
  }, [game.status, game.level, round]);
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) pause();
    };
    window.addEventListener('blur', pause);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('blur', pause);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [pause]);
  const start = () => {
    setGame(startGame());
    setRound((current) => current + 1);
    boardRef.current?.focus();
  };
  const resume = () => {
    setGame((current) => step(current, 'resume'));
    boardRef.current?.focus();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    const toggle = event.code === 'KeyP' || event.code === 'Escape';
    const action = ACTIONS[event.code];
    if (!toggle && !action) return;
    if (game.status !== 'playing' && game.status !== 'paused') return;
    event.preventDefault();
    event.stopPropagation();
    if (event.repeat && (toggle || !['left', 'right', 'down'].includes(action)))
      return;
    setGame((current) =>
      step(
        current,
        toggle ? (current.status === 'paused' ? 'resume' : 'pause') : action,
      ),
    );
  };
  const play = (action: Action) => setGame((current) => step(current, action));
  return { game, boardRef, start, pause, resume, onKeyDown, play };
}
