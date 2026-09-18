// relative-time.test.ts — U-M7 history-panel relative-time formatting.
//
// The panel's honesty contract: a version with no recorded timestamp (the
// OCR root — see core/page_history.py VersionEntry) must show that gap,
// never a fabricated value.

import { describe, it, expect } from "vitest";
import { formatRelativeTime, UNKNOWN_TIME_LABEL } from "./relative-time";

const NOW = Date.parse("2026-09-18T12:00:00Z");

describe("formatRelativeTime", () => {
  it("returns UNKNOWN_TIME_LABEL for null (the OCR root's honest gap)", () => {
    expect(formatRelativeTime(null, NOW)).toBe(UNKNOWN_TIME_LABEL);
  });

  it("returns UNKNOWN_TIME_LABEL for undefined", () => {
    expect(formatRelativeTime(undefined, NOW)).toBe(UNKNOWN_TIME_LABEL);
  });

  it("returns UNKNOWN_TIME_LABEL for an unparseable timestamp", () => {
    expect(formatRelativeTime("not-a-date", NOW)).toBe(UNKNOWN_TIME_LABEL);
  });

  it("renders under a minute as 'just now'", () => {
    const ts = new Date(NOW - 30_000).toISOString();
    expect(formatRelativeTime(ts, NOW)).toBe("just now");
  });

  it("renders minutes ago", () => {
    const ts = new Date(NOW - 5 * 60_000).toISOString();
    expect(formatRelativeTime(ts, NOW)).toBe("5 min ago");
  });

  it("renders hours ago", () => {
    const ts = new Date(NOW - 3 * 60 * 60_000).toISOString();
    expect(formatRelativeTime(ts, NOW)).toBe("3 hr ago");
  });

  it("renders days ago", () => {
    const ts = new Date(NOW - 2 * 24 * 60 * 60_000).toISOString();
    expect(formatRelativeTime(ts, NOW)).toBe("2 d ago");
  });

  it("falls back to an ISO date once older than a week", () => {
    const ts = new Date(NOW - 10 * 24 * 60 * 60_000).toISOString();
    expect(formatRelativeTime(ts, NOW)).toBe(ts.slice(0, 10));
  });

  it("treats a future timestamp (clock skew) as 'just now', never negative", () => {
    const ts = new Date(NOW + 5_000).toISOString();
    expect(formatRelativeTime(ts, NOW)).toBe("just now");
  });
});
