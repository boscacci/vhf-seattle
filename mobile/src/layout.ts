export const ANDROID_STATUS_BAR_FALLBACK_HEIGHT = 24;
export const ANDROID_TOP_CHROME_MIN_GUTTER = 44;
export const ANDROID_TOP_CHROME_EXTRA_GUTTER = 12;

export function topChromeGutter(platform: string, statusBarHeight?: number | null): number {
  if (platform !== "android") {
    return 0;
  }

  const measuredHeight =
    typeof statusBarHeight === "number" && Number.isFinite(statusBarHeight) && statusBarHeight > 0
      ? statusBarHeight
      : ANDROID_STATUS_BAR_FALLBACK_HEIGHT;

  return Math.max(
    ANDROID_TOP_CHROME_MIN_GUTTER,
    measuredHeight + ANDROID_TOP_CHROME_EXTRA_GUTTER,
  );
}
