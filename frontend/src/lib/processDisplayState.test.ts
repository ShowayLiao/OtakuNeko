import assert from 'node:assert/strict';
import { it } from 'vitest';

import {
  resolveProcessExpanded,
  resolveStepExpanded,
  selectPendingTool,
} from './processDisplayState';

it('keeps the latest completed step open until a successor starts', () => {
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

it('manual step visibility overrides automatic state', () => {
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

it('non-active completed steps stay closed and body-less steps stay closed', () => {
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

it('running process opens by default and completed process closes by default', () => {
  assert.equal(resolveProcessExpanded(true, true, null), true);
  assert.equal(resolveProcessExpanded(true, false, null), false);
});

it('manual process visibility takes priority over automatic state', () => {
  assert.equal(resolveProcessExpanded(true, true, false), false);
  assert.equal(resolveProcessExpanded(true, false, true), true);
  assert.equal(resolveProcessExpanded(false, true, true), false);
});

it('never guesses between concurrent pending tools with the same name', () => {
  const tools = [
    { name: 'search', sourceId: 'call-1', status: 'pending' },
    { name: 'search', sourceId: 'call-2', status: 'pending' },
  ];

  assert.equal(selectPendingTool(tools, 'search', 'call-2'), tools[1]);
  assert.equal(selectPendingTool(tools, 'search'), undefined);
  assert.equal(selectPendingTool([tools[0]], 'search'), tools[0]);
});
