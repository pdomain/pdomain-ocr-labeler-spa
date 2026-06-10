// WordImagePreview.tsx — Word image preview box + OCR/GT confidence bars (P2.b, Gap 29).
//
// Renders:
//   - A 76px-tall serif preview box with cream/off-white background, centred on
//     the OCR text glyph. Falls back to a text rendering when no image URL is
//     available (imageUrl is optional — wired in P3 Konva slice).
//   - Two horizontal confidence bars beneath: "OCR" and "GT".
//
// Confidence heuristic (no dedicated confidence field in WordMatch schema):
//   OCR confidence: fuzz_score (0–100) or 100 when exact match.
//   GT confidence:  100 when is_validated, else 50 when fuzz_score > 80, else 0.
//
// data-testids:
//   word-image-preview          — outer container
//   word-image-preview-box      — 76px cream preview box
//   word-image-preview-ocr-bar  — OCR confidence bar fill
//   word-image-preview-gt-bar   — GT confidence bar fill

import type { components } from "../../api/types";

type WordMatch = components["schemas"]["WordMatch"];
type BBox = components["schemas"]["BBox"];

export interface WordImagePreviewProps {
  word: WordMatch;
  /** Optional page or word image URL. */
  imageUrl?: string | undefined;
  /** Optional source-pixel crop from the full page image. */
  cropBBox?: BBox | undefined;
  /** Source page image width, required for SVG crop rendering. */
  sourceWidth?: number | undefined;
  /** Source page image height, required for SVG crop rendering. */
  sourceHeight?: number | undefined;
}

function ocrConfidence(word: WordMatch): number {
  if (word.match_status === "exact") return 100;
  if (word.fuzz_score != null) return Math.round(word.fuzz_score);
  if (word.match_status === "fuzzy") return 70;
  return 0;
}

function gtConfidence(word: WordMatch): number {
  if (word.is_validated) return 100;
  const ocr = ocrConfidence(word);
  if (ocr >= 80) return 50;
  return 0;
}

interface ConfidenceBarProps {
  label: string;
  pct: number;
  testid: string;
}

function ConfidenceBar({ label, pct, testid }: ConfidenceBarProps) {
  const clamped = Math.max(0, Math.min(100, pct));
  const barColor =
    clamped >= 80 ? "bg-status-exact" : clamped >= 50 ? "bg-status-fuzzy" : "bg-status-mismatch";

  return (
    <div className="flex items-center gap-2">
      <span className="w-7 text-[9px] font-mono text-ink-3 shrink-0">{label}</span>
      <div className="flex-1 h-[3px] bg-border-2 rounded-full overflow-hidden">
        <div
          data-testid={testid}
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${String(clamped)}%` }}
        />
      </div>
      <span className="w-6 text-right text-[9px] font-mono text-ink-3 shrink-0">{clamped}%</span>
    </div>
  );
}

export function WordImagePreview({
  word,
  imageUrl,
  cropBBox,
  sourceWidth,
  sourceHeight,
}: WordImagePreviewProps) {
  const ocrPct = ocrConfidence(word);
  const gtPct = gtConfidence(word);
  const canRenderCrop =
    imageUrl &&
    cropBBox &&
    sourceWidth &&
    sourceHeight &&
    cropBBox.width > 0 &&
    cropBBox.height > 0;
  const cropViewBox = canRenderCrop
    ? [cropBBox.x, cropBBox.y, cropBBox.width, cropBBox.height].map(String).join(" ")
    : "";

  return (
    <div data-testid="word-image-preview" className="flex flex-col gap-2 px-3 py-2">
      {/* 76px serif preview box */}
      <div
        data-testid="word-image-preview-box"
        className="w-full h-[76px] rounded border border-border-2 overflow-hidden flex items-center justify-center"
        style={{ background: "var(--bg-sunk)" }}
      >
        {canRenderCrop ? (
          <svg
            data-testid="word-image-crop"
            role="img"
            aria-label={word.ocr_text || "Word image crop"}
            viewBox={cropViewBox}
            className="h-full w-full"
            preserveAspectRatio="xMidYMid meet"
          >
            <image href={imageUrl} width={sourceWidth} height={sourceHeight} />
          </svg>
        ) : imageUrl ? (
          /* When a real image URL is available, show it */
          <img
            src={imageUrl}
            alt={word.ocr_text}
            className="max-h-full max-w-full object-contain"
          />
        ) : (
          /* Fallback: render OCR text in a serif font */
          <span
            className="text-[28px] leading-none text-ink-1 select-none px-2"
            style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
          >
            {word.ocr_text || <span className="text-ink-4 text-base italic">∅</span>}
          </span>
        )}
      </div>

      {/* Confidence bars */}
      <div className="flex flex-col gap-1">
        <ConfidenceBar label="OCR" pct={ocrPct} testid="word-image-preview-ocr-bar" />
        <ConfidenceBar label="GT" pct={gtPct} testid="word-image-preview-gt-bar" />
      </div>
    </div>
  );
}
