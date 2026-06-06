// PlaintextGtOcrView.tsx — Shared visible full-page GT/OCR read-only text view.
//
// S2.2: Extracted from TextTabs GT/OCR panel logic so it can be mounted
// visibly in the Drawer "Text" tab without duplicating the textarea logic.
//
// Distinct testids (vs. the hidden-stub TextTabs panels) so tests and
// Playwright selectors can target the visible instance:
//   drawer-text-panel-ground-truth — read-only GT textarea
//   drawer-text-panel-ocr          — read-only OCR textarea

interface PlaintextGtOcrViewProps {
  pageTextGt?: string | null | undefined;
  pageTextOcr?: string | null | undefined;
}

export function PlaintextGtOcrView({ pageTextGt = "", pageTextOcr = "" }: PlaintextGtOcrViewProps) {
  return (
    <div className="flex flex-col gap-2 p-2 h-full overflow-hidden">
      <div className="flex flex-col flex-1 min-h-0">
        <span className="text-[9px] font-semibold tracking-wider uppercase text-ink-3 mb-0.5">
          Ground Truth
        </span>
        <textarea
          data-testid="drawer-text-panel-ground-truth"
          readOnly
          value={pageTextGt ?? ""}
          className="flex-1 resize-none font-mono text-sm p-2 border border-border-1 rounded bg-bg-sunk focus:outline-none"
          aria-label="Ground truth text"
        />
      </div>
      <div className="flex flex-col flex-1 min-h-0">
        <span className="text-[9px] font-semibold tracking-wider uppercase text-ink-3 mb-0.5">
          OCR
        </span>
        <textarea
          data-testid="drawer-text-panel-ocr"
          readOnly
          value={pageTextOcr ?? ""}
          className="flex-1 resize-none font-mono text-sm p-2 border border-border-1 rounded bg-bg-sunk focus:outline-none"
          aria-label="OCR text"
        />
      </div>
    </div>
  );
}
