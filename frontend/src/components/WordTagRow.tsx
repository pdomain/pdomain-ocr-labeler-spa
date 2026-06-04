// WordTagRow.tsx — Style/scope/component tag row for the word-edit dialog (#212)
// Spec: docs/specs/2026-05-12-word-edit-dialog-design.md §Action rows
//      docs/architecture/07-word-edit-dialog.md §3.3 (tag row)
//
// Style select + Scope select -> Apply Style.
// Component select -> Apply Component + Clear Component.
//
// Label vocab is sourced from useLabelVocabulary() (canonical book-tools values)
// so this component can never POST a non-canonical label to the backend.
// Explicit styleOptions/componentOptions props override the hook (for tests /
// call sites that already hold a resolved list).
//
// driver-contract testids:
//   dialog-style-select           — style label selector
//   dialog-scope-select           — scope selector ("whole" | "part")
//   dialog-component-select       — component label selector
//   dialog-apply-style-button     — POST .../style
//   dialog-apply-component-button — POST .../component {enabled:true}
//   dialog-clear-component-button — POST .../component {enabled:false}

import { useState } from "react";
import {
  useLabelVocabulary,
  FALLBACK_STYLES,
  FALLBACK_COMPONENTS,
} from "../hooks/useLabelVocabulary";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WordTagRowProps {
  /** Available style labels (from backend metadata). When omitted, the
   *  canonical list from useLabelVocabulary() is used. */
  styleOptions?: string[] | undefined;
  /** Available component labels. When omitted, the canonical list from
   *  useLabelVocabulary() is used. */
  componentOptions?: string[] | undefined;
  /** Called with style + scope when Apply Style is clicked. */
  onApplyStyle?: ((style: string, scope: "whole" | "part") => Promise<void>) | undefined;
  /** Called with component + enabled when Apply/Clear Component is clicked. */
  onApplyComponent?: ((component: string, enabled: boolean) => Promise<void>) | undefined;
}

// ---------------------------------------------------------------------------
// WordTagRow
// ---------------------------------------------------------------------------

export function WordTagRow({
  styleOptions,
  componentOptions,
  onApplyStyle,
  onApplyComponent,
}: WordTagRowProps) {
  // Source canonical vocab from the backend (or its FALLBACK_* lists).
  // When explicit props are provided they take priority over the hook's values.
  const vocab = useLabelVocabulary();
  const resolvedStyles = styleOptions ?? vocab.textStyleLabels;
  const resolvedComponents = componentOptions ?? vocab.wordComponents;

  // Default selected values must be canonical.  Use the first element of the
  // resolved list; fall back to a known-canonical literal so the initializer
  // is always a valid value even before the hook has populated the list.
  const [style, setStyle] = useState<string>(resolvedStyles[0] ?? FALLBACK_STYLES[0] ?? "italics");
  const [scope, setScope] = useState<"whole" | "part">("whole");
  const [component, setComponent] = useState<string>(
    resolvedComponents[0] ?? FALLBACK_COMPONENTS[0] ?? "drop cap",
  );

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
          {resolvedStyles.map((s) => (
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
          {resolvedComponents.map((c) => (
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
