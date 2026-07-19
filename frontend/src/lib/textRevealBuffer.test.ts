import assert from 'node:assert/strict';
import { it } from 'vitest';

import { KeyedTextRevealQueue, TextRevealBuffer, revealCharactersPerFrame } from './textRevealBuffer';

it('reveals a burst over multiple display ticks', () => {
  const buffer = new TextRevealBuffer();

  buffer.append('abcdef');

  assert.equal(buffer.take(2), 'ab');
  assert.equal(buffer.take(2), 'cd');
  assert.equal(buffer.take(2), 'ef');
  assert.equal(buffer.hasPending(), false);
});

it('can discard text that has not been displayed after stop', () => {
  const buffer = new TextRevealBuffer();
  buffer.append('already received');

  buffer.clear();

  assert.equal(buffer.take(20), '');
  assert.equal(buffer.hasPending(), false);
});

it('never splits an emoji while revealing text', () => {
  const buffer = new TextRevealBuffer();
  buffer.append('猫🐱番');

  assert.equal(buffer.take(2), '猫🐱');
  assert.equal(buffer.take(1), '番');
});

it('reveals reasoning and tool payloads independently in the same frame', () => {
  const queue = new KeyedTextRevealQueue();
  queue.append('thought-1', 'details', 'abcdef');
  queue.append('tool-1', 'output', '123456');

  assert.deepEqual(queue.takeFrame(() => 2), [
    { nodeId: 'thought-1', field: 'details', text: 'ab' },
    { nodeId: 'tool-1', field: 'output', text: '12' },
  ]);
  assert.equal(queue.hasPending('thought-1'), true);
  assert.equal(queue.hasPending('tool-1'), true);

  queue.takeFrame(() => 20);
  assert.equal(queue.hasPending(), false);
});

it('can discard every queued process frame after stop or error', () => {
  const queue = new KeyedTextRevealQueue();
  queue.append('thought-1', 'details', 'hidden reasoning');
  queue.append('tool-1', 'output', 'hidden result');

  queue.clear();

  assert.deepEqual(queue.takeFrame(() => 20), []);
  assert.equal(queue.hasPending(), false);
});

it('uses an adaptive frame size without dumping small bursts at once', () => {
  assert.equal(revealCharactersPerFrame(20), 1);
  assert.equal(revealCharactersPerFrame(100), 3);
  assert.equal(revealCharactersPerFrame(500), 10);
  assert.equal(revealCharactersPerFrame(1000), 16);
});
