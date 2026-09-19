import { Button } from '@open-work-hub/ui';
import { useTranslation } from 'react-i18next';
import { SHAPES, visibleBoard, type Cell, type Kind } from './engine';
import { useTetris } from './use-tetris';

const BLOCK_STYLES: Record<Kind, string> = {
  I: 'bg-app-chart-7/25 border-app-chart-7',
  J: 'bg-app-chart-1/25 border-app-chart-1',
  L: 'bg-app-chart-4/25 border-app-chart-4',
  O: 'bg-app-chart-6/25 border-app-chart-6',
  S: 'bg-app-chart-2/25 border-app-chart-2',
  T: 'bg-app-chart-3/25 border-app-chart-3',
  Z: 'bg-app-chart-5/25 border-app-chart-5',
};

function Block({ cell }: { cell: Cell }) {
  return (
    <span
      data-cell={cell ?? ''}
      className={`flex aspect-square min-w-0 items-center justify-center border text-[10px] font-semibold text-app-ink ${cell ? BLOCK_STYLES[cell] : 'border-app-border/50 bg-app-surface'}`}
    >
      {cell}
    </span>
  );
}
function Preview({
  kind,
  label,
  empty,
}: {
  kind: Kind | undefined | null;
  label: string;
  empty: string;
}) {
  return (
    <div>
      <h2 className="app-text-body mb-2 font-medium">{label}</h2>
      <div
        role="img"
        aria-label={kind ? `${label}: ${kind}` : `${label}: ${empty}`}
        className="h-16 w-16"
      >
        {kind ? (
          <div
            aria-hidden="true"
            className="grid"
            style={{
              gridTemplateColumns: `repeat(${SHAPES[kind].length}, 1fr)`,
            }}
          >
            {SHAPES[kind].flat().map((cell, index) => (
              <Block key={index} cell={cell ? kind : null} />
            ))}
          </div>
        ) : (
          <span className="app-text-body text-app-ink-muted">{empty}</span>
        )}
      </div>
    </div>
  );
}
export function TetrisView() {
  const { t } = useTranslation('apps');
  const { game, boardRef, start, pause, resume, onKeyDown, play } = useTetris();
  const controls = [
    { action: 'counterclockwise', label: t('tetris.Rotate left'), symbol: '↶' },
    { action: 'hold', label: t('tetris.Hold block'), symbol: 'C' },
    { action: 'clockwise', label: t('tetris.Rotate right'), symbol: '↷' },
    { action: 'left', label: t('tetris.Move left'), symbol: '←' },
    { action: 'down', label: t('tetris.Soft drop'), symbol: '↓' },
    { action: 'right', label: t('tetris.Move right'), symbol: '→' },
    { action: 'drop', label: t('tetris.Drop instantly'), symbol: '⇓' },
  ] as const;
  const status = {
    ready: t('tetris.Ready to play'),
    playing: t('tetris.Playing'),
    paused: t('tetris.Paused — resume when ready'),
    over: t('tetris.Game over'),
  }[game.status];
  return (
    <section
      className="h-full overflow-auto bg-app-bg p-4 text-app-ink"
      aria-labelledby="tetris-title"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          pause();
      }}
    >
      <header className="mb-4 flex flex-wrap items-center gap-3">
        <h1 id="tetris-title" className="app-text-title-lg">
          {t('tetris.Tetris')}
        </h1>
        {game.status === 'ready' ? (
          <Button variant="primary" onClick={start}>
            {t('tetris.Start game')}
          </Button>
        ) : (
          <>
            {game.status === 'playing' && (
              <Button variant="secondary" onClick={pause}>
                {t('tetris.Pause game')}
              </Button>
            )}
            {game.status === 'paused' && (
              <Button variant="primary" onClick={resume}>
                {t('tetris.Resume game')}
              </Button>
            )}
            <Button variant="secondary" onClick={start}>
              {t('tetris.Restart game')}
            </Button>
          </>
        )}
        <p role="status" className="app-text-body text-app-ink-muted">
          {status}
        </p>
      </header>
      <div className="grid max-w-[420px] grid-cols-[minmax(0,1fr)_88px] items-start gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
        <div
          ref={boardRef}
          role="region"
          aria-label={t('tetris.Game board')}
          aria-describedby="tetris-controls"
          tabIndex={0}
          onKeyDown={onKeyDown}
          className="mx-auto w-[clamp(140px,calc((100dvh-350px)/2),280px)] max-w-full rounded-sm border border-app-border outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
        >
          <div aria-hidden="true" className="grid grid-cols-10">
            {visibleBoard(game)
              .flat()
              .map((cell, index) => (
                <Block key={index} cell={cell} />
              ))}
          </div>
        </div>
        <div
          role="group"
          aria-label={t('tetris.Screen controls')}
          className="col-span-2 row-start-2 grid grid-cols-3 gap-2"
        >
          {controls.map(({ action, label, symbol }) => (
            <Button
              key={action}
              variant="secondary"
              className={`min-h-11 min-w-0 flex-col gap-0 px-1 touch-manipulation select-none ${action === 'drop' ? 'col-span-3' : ''}`}
              disabled={
                game.status !== 'playing' ||
                (action === 'hold' && !game.canHold)
              }
              onClick={() => play(action)}
              aria-label={label}
              title={label}
            >
              <span aria-hidden="true">{symbol}</span>
              <span>{label}</span>
            </Button>
          ))}
        </div>
        <aside className="col-start-2 row-start-1 space-y-3">
          <dl className="grid gap-2 app-text-body">
            <div>
              <dt className="text-app-ink-muted">{t('tetris.Score')}</dt>
              <dd
                data-testid="tetris-score"
                className="app-text-title-lg tabular-nums"
              >
                {game.score}
              </dd>
            </div>
            <div>
              <dt className="text-app-ink-muted">{t('tetris.Lines')}</dt>
              <dd className="app-text-title-lg tabular-nums">{game.lines}</dd>
            </div>
            <div>
              <dt className="text-app-ink-muted">{t('tetris.Level')}</dt>
              <dd className="app-text-title-lg tabular-nums">{game.level}</dd>
            </div>
          </dl>
          <div className="flex flex-col gap-3">
            <Preview
              kind={game.queue[0]}
              label={t('tetris.Next block')}
              empty={t('tetris.Empty')}
            />
            <Preview
              kind={game.hold}
              label={t('tetris.Hold')}
              empty={t('tetris.Empty')}
            />
          </div>
        </aside>
        <div
          id="tetris-controls"
          className="col-span-2 space-y-2 app-text-body text-app-ink-muted"
        >
          <h2 className="font-medium text-app-ink">
            {t('tetris.Keyboard controls')}
          </h2>
          <p>{t('tetris.Arrows move; down drops faster')}</p>
          <p>
            {t('tetris.Up or X rotates clockwise; Z rotates counterclockwise')}
          </p>
          <p>{t('tetris.Space drops instantly; C holds a block')}</p>
          <p>{t('tetris.P or Esc pauses or resumes')}</p>
          <p>{t('tetris.Leaving the game pauses it; resume explicitly')}</p>
          <p>{t('tetris.Progress is not saved when you leave or reload')}</p>
        </div>
      </div>
    </section>
  );
}
