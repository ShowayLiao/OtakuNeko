import assert from 'node:assert/strict';
import test from 'node:test';

// @ts-ignore Node's built-in TypeScript runner requires the explicit extension.
import {
  resolveProcessExpanded,
  resolveStepExpanded,
  selectPendingTool,
} from './processDisplayState.ts';

test('keeps the latest completed step open until a successor starts', () => {
  assert.equal(resolveStepExpanded({
    hasBody: true,
    isAutoActive: true,
    userExpanded: null,
  }), true);
  assert.equal(resolveStepExpanded({
    hasBody: true,
    isAutoActive: false,
    userExpanded: null,
  }), false);
});

test('manual step visibility overrides automatic state', () => {
  assert.equal(resolveStepExpanded({
    hasBody: true,
    isAutoActive: true,
    userExpanded: false,
  }), false);
  assert.equal(resolveStepExpanded({
    hasBody: true,
    isAutoActive: false,
    userExpanded: true,
  }), true);
});

test('non-active completed steps stay closed and body-less steps stay closed', () => {
  assert.equal(resolveStepExpanded({
    hasBody: true,
    isAutoActive: false,
    userExpanded: null,
  }), false);
  assert.equal(resolveStepExpanded({
    hasBody: false,
    isAutoActive: true,
    userExpanded: null,
  }), false);
});

test('running process opens by default and completed process closes by default', () => {
  assert.equal(resolveProcessExpanded(true, true, null), true);
  assert.equal(resolveProcessExpanded(true, false, null), false);
});

test('manual process visibility takes priority over automatic state', () => {
  assert.equal(resolveProcessExpanded(true, true, false), false);
  assert.equal(resolveProcessExpanded(true, false, true), true);
  assert.equal(resolveProcessExpanded(false, true, true), false);
});

test('never guesses between concurrent pending tools with the same name', () => {
  const tools = [
    { name: 'search', sourceId: 'call-1', status: 'pending' },
    { name: 'search', sourceId: 'call-2', status: 'pending' },
  ];

  assert.equal(selectPendingTool(tools, 'search', 'call-2'), tools[1]);
  assert.equal(selectPendingTool(tools, 'search'), undefined);
  assert.equal(selectPendingTool([tools[0]], 'search'), tools[0]);
});
