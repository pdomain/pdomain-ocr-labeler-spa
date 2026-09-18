// relative-time.ts — small, honest "N units ago" formatter.
//
// U-M7 (docs/specs/2026-06-12-event-store-undo.md "history panel"): each
// history-panel row shows a relative time derived from the version's real
// `ProvenanceNode.timestamp`. This formatter never invents a timestamp —
// callers pass `null`/`undefined` straight through to `formatRelativeTime`,
// which returns a fixed "unknown time" string rather than fabricating a
// value from other data. The one entry that has no timestamp by
// construction is the OCR-ingest root row (`core/page_history.py`
// `VersionEntry` docstring); everything else the labeler writes always
// stamps `datetime.now(UTC)`.

/** Shown for a version with no recorded timestamp — never fabricated. */
export const UNKNOWN_TIME_LABEL = "time unknown";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

/**
 * Render `isoTimestamp` relative to `now` (defaults to `Date.now()`) as a
 * short, human string: "just now", "5 min ago", "3 hr ago", "2 d ago", or
 * the ISO date once older than a week. Returns `UNKNOWN_TIME_LABEL` for
 * `null`/`undefined`/an unparseable string — the caller's honest-timestamp
 * contract, not a formatting fallback to hide behind.
 */
export function formatRelativeTime(
  isoTimestamp: string | null | undefined,
  now: number = Date.now(),
): string {
  if (isoTimestamp == null) return UNKNOWN_TIME_LABEL;
  const then = Date.parse(isoTimestamp);
  if (Number.isNaN(then)) return UNKNOWN_TIME_LABEL;

  const deltaMs = now - then;
  if (deltaMs < 0) return "just now"; // clock skew guard — never show negative time
  if (deltaMs < MINUTE_MS) return "just now";
  if (deltaMs < HOUR_MS) return `${String(Math.floor(deltaMs / MINUTE_MS))} min ago`;
  if (deltaMs < DAY_MS) return `${String(Math.floor(deltaMs / HOUR_MS))} hr ago`;
  if (deltaMs < 7 * DAY_MS) return `${String(Math.floor(deltaMs / DAY_MS))} d ago`;
  return new Date(then).toISOString().slice(0, 10);
}
