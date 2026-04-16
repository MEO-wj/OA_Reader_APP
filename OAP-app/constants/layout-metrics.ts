export const TOP_BAR_LAYOUT = {
  homeTopPadding: 10,
  homeBlurBottom: 6,
  homeBarVertical: 7,
  exploreTopPadding: 8,
  exploreBarHorizontal: 14,
  exploreBarVertical: 8,
  exploreTitleMarginTop: 0,
} as const;

export const BOTTOM_DOCK_LAYOUT = {
  bottomOffset: 12,
  horizontalPadding: 20,
  verticalPadding: 8,
  innerGap: 18,
  buttonSize: 40,
  buttonRadius: 14,
} as const;

export const CHAT_INPUT_LAYOUT = {
  outerHorizontal: 14,
  outerBottom: 4,
  shellRadius: 22,
  shellPadding: 4,
  inputHorizontalLeft: 15,
  inputHorizontalRight: 48,
  inputVertical: 9,
  sendButtonSize: 34,
  sendButtonRight: 6,
  sendButtonTop: 6,
} as const;

export function getBottomDockHeight() {
  return BOTTOM_DOCK_LAYOUT.buttonSize + BOTTOM_DOCK_LAYOUT.verticalPadding * 2;
}

export function getTabContentBottomPadding(extraGap = 12) {
  return getBottomDockHeight() + BOTTOM_DOCK_LAYOUT.bottomOffset + extraGap;
}

export function getChatInputDockOffset() {
  return getBottomDockHeight() + BOTTOM_DOCK_LAYOUT.bottomOffset - 6;
}
