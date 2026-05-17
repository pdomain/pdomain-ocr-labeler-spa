// WordTagRow.tsx — Style/scope/component tag row for the word-edit dialog (#212)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//      docs/architecture/07-word-edit-dialog.md §3.3 (tag row)
//
// Style select + Scope select -> Apply Style.
// Component select -> Apply Component + Clear Component.
//
// driver-contract testids:
//   dialog-style-select           — style label selector
//   dialog-scope-select           — scope selector ("whole" | "part")
//   dialog-component-select       — component label selector
//   dialog-apply-style-button     — POST .../style
//   dialog-apply-component-button — POST .../component {enabled:true}
//   dialog-clear-component-button — POST .../component {enabled:false}

import { useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WordTagRowProps {
  /** Available style labels (from backend metadata). */
  styleOptions?: string[] | undefined;
  /** Available component labels. */
  componentOptions?: string[] | undefined;
  /** Called with style + scope when Apply Style is clicked. */
  onApplyStyle?: ((style: string, scope: "whole" | "part") => Promise<void>) | undefined;
  /** Called with component + enabled when Apply/Clear Component is clicked. */
  onApplyComponent?: ((component: string, enabled: boolean) => Promise<void>) | undefined;
}

// ---------------------------------------------------------------------------
// Constants — default label lists matching legacy spec §3.3
// ---------------------------------------------------------------------------

const DEFAULT_STYLES = [
  "italic",
  "bold",
  "small_caps",
  "bold_italic",
  "antiqua",
  "gesperrt",
  "blackletter",
  "handwritten",
];

const DEFAULT_COMPONENTS = [
  "footnote",
  "footnote_marker",
  "drop_cap",
  "sidenote",
  "caption",
  "header",
  "footer",
  "page_number",
  "catchword",
  "signature",
];

// ---------------------------------------------------------------------------
// WordTagRow
// ---------------------------------------------------------------------------

export function WordTagRow({
  styleOptions = DEFAULT_STYLES,
  componentOptions = DEFAULT_COMPONENTS,
  onApplyStyle,
  onApplyComponent,
}: WordTagRowProps) {
  const [style, setStyle] = useState<string>(styleOptions[0] ?? "italic");
  const [scope, setScope] = useState<"whole" | "part">("whole");
  const [component, setComponent] = useState<string>(componentOptions[0] ?? "footnote");

  return (
    <div className="flex flex-col gap-1.5 w-full pt-1 border-t border-border-1">
      {/* Style row */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-ink-3 w-14 shrink-0 font-medium">Style</span>
        <select
          data-testid="dialog-style-select"
          value={style}
          onChange={(e) => {
            setStyle(e.target.value);
          }}
          className="text-xs border border-border-2 rounded px-1 py-0.5 bg-bg-surface text-ink-1"
        >
          {styleOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          data-testid="dialog-scope-select"
          value={scope}
          onChange={(e) => {
            setScope(e.target.value as "whole" | "part");
          }}
          className="text-xs border border-border-2 rounded px-1 py-0.5 bg-bg-surface text-ink-1"
        >
          <option value="whole">whole</option>
          <option value="part">part</option>
        </select>
        <button
          data-testid="dialog-apply-style-button"
          onClick={() => {
            void onApplyStyle?.(style, scope);
          }}
          className="px-2 py-1 text-xs rounded border border-accent bg-bg-surface text-accent hover:bg-bg-raised transition-colors"
        >
          Apply
        </button>
      </div>

      {/* Component row */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-xs text-ink-3 w-14 shrink-0 font-medium">Comp.</span>
        <select
          data-testid="dialog-component-select"
          value={component}
          onChange={(e) => {
            setComponent(e.target.value);
          }}
          className="text-xs border border-border-2 rounded px-1 py-0.5 bg-bg-surface text-ink-1"
        >
          {componentOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button
          data-testid="dialog-apply-component-button"
          onClick={() => {
            void onApplyComponent?.(component, true);
          }}
          className="px-2 py-1 text-xs rounded border border-status-exact bg-bg-surface text-status-exact hover:bg-bg-raised transition-colors"
        >
          Set
        </button>
        <button
          data-testid="dialog-clear-component-button"
          onClick={() => {
            void onApplyComponent?.(component, false);
          }}
          className="px-2 py-1 text-xs rounded border border-border-2 bg-bg-surface text-ink-2 hover:bg-bg-raised transition-colors"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
