import test from 'node:test';
import assert from 'node:assert/strict';

import {
  BOTTOM_DOCK_LAYOUT,
  CHAT_INPUT_LAYOUT,
  TOP_BAR_LAYOUT,
  getBottomDockHeight,
  getChatInputDockOffset,
  getTabContentBottomPadding,
} from './layout-metrics.ts';

test('layout metrics keep top bar and dock more compact than previous oversized values', () => {
  assert.equal(TOP_BAR_LAYOUT.exploreTopPadding < 44, true);
  assert.equal(BOTTOM_DOCK_LAYOUT.bottomOffset < 24, true);
  assert.equal(CHAT_INPUT_LAYOUT.sendButtonSize < 40, true);
});

test('bottom dock helpers reserve enough space for scroll content and chat composer', () => {
  const dockHeight = getBottomDockHeight();

  assert.equal(dockHeight, 56);
  assert.equal(getTabContentBottomPadding() > dockHeight, true);
  assert.equal(getChatInputDockOffset() < getTabContentBottomPadding(), true);
  assert.equal(getChatInputDockOffset() >= dockHeight, true);
});
