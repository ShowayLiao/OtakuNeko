import { describe, expect, it } from 'vitest';
import { createRafBatcher } from './rafBatcher';

describe('createRafBatcher', () => {
  it('coalesces multiple schedules into one frame', () => {
    const frames: Array<() => void> = [];
    const run = createRafBatcher((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const calls: string[] = [];

    run(() => calls.push('first'));
    run(() => calls.push('latest'));

    expect(frames).toHaveLength(1);
    expect(calls).toEqual([]);
    frames[0]();
    expect(calls).toEqual(['latest']);
  });

  it('can be cancelled before the frame runs', () => {
    const frames: Array<() => void> = [];
    const run = createRafBatcher((callback) => {
      frames.push(callback);
      return frames.length;
    });
    const calls: string[] = [];

    run(() => calls.push('cancelled'));
    run.cancel();
    frames[0]();

    expect(calls).toEqual([]);
  });
});
