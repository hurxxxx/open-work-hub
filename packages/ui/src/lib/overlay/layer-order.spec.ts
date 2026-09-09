import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const styles = readFileSync(
  resolve(import.meta.dirname, '../../../styles.css'),
  'utf8',
);

function layer(name: string): number {
  const match = styles.match(new RegExp(`--ui-z-${name}:\\s*(\\d+)\\s*;`));
  if (!match) throw new Error(`Missing layer token: ${name}`);
  return Number(match[1]);
}

describe('shared overlay hierarchy', () => {
  it('covers persistent widget surfaces with modal overlays', () => {
    expect(layer('dock')).toBeGreaterThan(layer('floating-panel'));
    expect(layer('drawer') - 1).toBeGreaterThan(layer('dock'));
  });

  it('keeps confirmations and their popovers above the underlying modal', () => {
    expect(layer('dialog-elevated') - 1).toBeGreaterThan(layer('drawer'));
    expect(layer('popover')).toBeGreaterThan(layer('dialog-elevated'));
    expect(layer('toast')).toBeGreaterThan(layer('popover'));
  });
});
