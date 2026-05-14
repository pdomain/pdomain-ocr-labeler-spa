// ToolbarActionGrid.tsx — 4×14 toolbar grid + Apply Style row + Add Word row (#207)
// Spec: docs/specs/2026-05-12-toolbar-actions-design.md
//
// Grid: 4 rows (page/para/line/word) × 14 action columns.
// Each cell: data-testid="toolbar-{scope}-{action}"
// Absent cells (not valid for a scope): data-testid-stub="true", always disabled.
// Disabled state computed by useToolbarButtonStates.
//
// Apply Style row: apply-style-select, apply-scope-select, apply-component-select,
//   apply-style-button, clear-style-button
// Add Word row: add-word-button

import {
  useToolbarButtonStates,
  type ButtonStates,
  type PageData,
  type Selection,
} from "../hooks/useToolbarButtonStates";

// ─── Grid layout constants ────────────────────────────────────────────────

// 14 action columns (position 0…13)
const ACTIONS = [
  "merge",
  "refine",
  "expand-refine",
  "expand",
  "split-after",
  "split-selected",
  "w-to-l",
  "to-para",
  "gt-to-ocr",
  "ocr-to-gt",
  "validate",
  "unvalidate",
  "delete",
  // Column 14 is reserved for future use (stub only)
  "reserved",
] as const;

type ActionKey = (typeof ACTIONS)[number];
type RowScope = "page" | "para" | "line" | "word";

// Map action column → ButtonStates key for each scope. Null = stub (absent cell).
type ScopeMap = Partial<Record<ActionKey, keyof ButtonStates>>;

const PAGE_MAP: ScopeMap = {
  refine: "page_refine",
  "expand-refine": "page_expand_refine",
  expand: "page_expand",
  "gt-to-ocr": "page_gt_to_ocr",
  "ocr-to-gt": "page_ocr_to_gt",
  validate: "page_validate",
  unvalidate: "page_unvalidate",
};

const PARA_MAP: ScopeMap = {
  merge: "para_merge",
  refine: "para_refine",
  "expand-refine": "para_expand_refine",
  expand: "para_expand",
  "split-after": "para_split_after",
  "split-selected": "para_split_selected",
  "gt-to-ocr": "para_gt_to_ocr",
  "ocr-to-gt": "para_ocr_to_gt",
  validate: "para_validate",
  unvalidate: "para_unvalidate",
  delete: "para_delete",
};

const LINE_MAP: ScopeMap = {
  merge: "line_merge",
  refine: "line_refine",
  "expand-refine": "line_expand_refine",
  expand: "line_expand",
  "split-after": "line_split_after",
  "split-selected": "line_split_selected",
  "to-para": "line_to_para",
  "gt-to-ocr": "line_gt_to_ocr",
  "ocr-to-gt": "line_ocr_to_gt",
  validate: "line_validate",
  unvalidate: "line_unvalidate",
  delete: "line_delete",
};

const WORD_MAP: ScopeMap = {
  refine: "word_refine",
  "expand-refine": "word_expand_refine",
  expand: "word_expand",
  "w-to-l": "word_w_to_l",
  "to-para": "word_to_para",
  "gt-to-ocr": "word_gt_to_ocr",
  "ocr-to-gt": "word_ocr_to_gt",
  validate: "word_validate",
  unvalidate: "word_unvalidate",
  delete: "word_delete",
};

const SCOPE_MAPS: Record<RowScope, ScopeMap> = {
  page: PAGE_MAP,
  para: PARA_MAP,
  line: LINE_MAP,
  word: WORD_MAP,
};

// Human-readable action labels
const ACTION_LABELS: Record<ActionKey, string> = {
  merge: "Merge",
  refine: "Refine",
  "expand-refine": "Exp+Ref",
  expand: "Expand",
  "split-after": "SplitAfter",
  "split-selected": "SplitSel",
  "w-to-l": "W→L",
  "to-para": "→Para",
  "gt-to-ocr": "GT→OCR",
  "ocr-to-gt": "OCR→GT",
  validate: "Validate",
  unvalidate: "Unval",
  delete: "Delete",
  reserved: "—",
};

// Text-style labels (would come from pd-book-tools; hardcoded here until API exposes them)
const TEXT_STYLE_LABELS = [
  "italic",
  "bold",
  "small_caps",
  "superscript",
  "subscript",
  "underline",
  "strikethrough",
];

// Word component labels (same)
const WORD_COMPONENT_LABELS = [
  "footnote_marker",
  "footnote_text",
  "drop_cap",
  "header",
  "footer",
  "page_number",
  "running_title",
];

// ─── Component ────────────────────────────────────────────────────────────

export interface ToolbarActionGridProps {
  selection: Selection;
  pageData: PageData;
  /** Override computed button states (e.g. for testing). */
  buttonStatesOverride?: Partial<ButtonStates>;
  /** Called when a non-stub, non-disabled action cell is clicked. */
  onAction: (key: keyof ButtonStates) => void;
  onApplyStyle: () => void;
  onClearStyle: () => void;
  addWordActive: boolean;
  onAddWordToggle: () => void;
}

/**
 * Toolbar action grid: 4 rows × 14 columns (page/para/line/word scopes).
 *
 * Each button:
 * - data-testid="toolbar-{scope}-{action}"
 * - data-testid-stub="true" for absent (invalid) cells
 * - disabled when buttonStates[key] is false or cell is a stub
 *
 * Below the grid: Apply Style row and Add Word row.
 */
export function ToolbarActionGrid({
  selection,
  pageData,
  buttonStatesOverride,
  onAction,
  onApplyStyle,
  onClearStyle,
  addWordActive,
  onAddWordToggle,
}: ToolbarActionGridProps) {
  const computed = useToolbarButtonStates(selection, pageData);
  const states: ButtonStates = { ...computed, ...buttonStatesOverride };

  const ROWS: RowScope[] = ["page", "para", "line", "word"];

  return (
    <div
      data-testid="toolbar-action-grid"
      className="flex flex-col gap-1 p-1 bg-gray-50 border-b border-gray-200 text-xs"
    >
      {/* 4 × 14 action grid */}
      <div className="grid" style={{ gridTemplateColumns: "4rem repeat(14, minmax(0, 1fr))" }}>
        {/* Column headers */}
        <div className="px-1 py-0.5 text-gray-400 font-medium text-center" />
        {ACTIONS.map((action) => (
          <div
            key={action}
            className="px-0.5 py-0.5 text-gray-400 text-center truncate"
            title={ACTION_LABELS[action]}
          >
            {ACTION_LABELS[action]}
          </div>
        ))}

        {/* Data rows */}
        {ROWS.map((scope) => {
          const scopeMap = SCOPE_MAPS[scope];
          return [
            // Row label
            <div
              key={`${scope}-label`}
              className="px-1 py-0.5 text-gray-600 font-medium capitalize self-center"
            >
              {scope}
            </div>,
            // Action cells
            ...ACTIONS.map((action) => {
              const stateKey = scopeMap[action];
              const isStub = stateKey == null;
              const isEnabled = !isStub && states[stateKey];
              const testId = `toolbar-${scope}-${action}`;

              return (
                <button
                  key={`${scope}-${action}`}
                  data-testid={testId}
                  data-testid-stub={isStub ? "true" : undefined}
                  disabled={!isEnabled}
                  title={isStub ? undefined : `${scope} ${ACTION_LABELS[action]}`}
                  onClick={() => {
                    if (!isStub && stateKey && isEnabled) {
                      onAction(stateKey);
                    }
                  }}
                  className={[
                    "m-0.5 py-0.5 text-xs rounded border transition-colors truncate",
                    isStub
                      ? "border-transparent bg-transparent text-transparent cursor-default"
                      : isEnabled
                        ? "border-gray-300 bg-white hover:bg-blue-50 hover:border-blue-400 text-gray-700"
                        : "border-gray-200 bg-gray-100 text-gray-300 cursor-default",
                  ].join(" ")}
                >
                  {isStub ? "·" : ACTION_LABELS[action]}
                </button>
              );
            }),
          ];
        })}
      </div>

      {/* Apply Style row */}
      <div className="flex items-center gap-2 px-1 py-0.5 flex-wrap">
        <select
          data-testid="apply-style-select"
          className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white"
          aria-label="Text style"
          defaultValue=""
        >
          <option value="" disabled>
            Style…
          </option>
          {TEXT_STYLE_LABELS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select
          data-testid="apply-scope-select"
          className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white"
          aria-label="Apply scope"
          defaultValue="whole"
        >
          <option value="whole">whole</option>
          <option value="part">part</option>
        </select>

        <select
          data-testid="apply-component-select"
          className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white"
          aria-label="Word component"
          defaultValue=""
        >
          <option value="" disabled>
            Component…
          </option>
          {WORD_COMPONENT_LABELS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <button
          data-testid="apply-style-button"
          onClick={onApplyStyle}
          className="px-2 py-0.5 text-xs rounded border border-gray-300 bg-white hover:bg-blue-50 hover:border-blue-400 text-gray-700 transition-colors"
        >
          Apply
        </button>

        <button
          data-testid="clear-style-button"
          onClick={onClearStyle}
          className="px-2 py-0.5 text-xs rounded border border-gray-300 bg-white hover:bg-red-50 hover:border-red-400 text-gray-700 transition-colors"
        >
          Clear
        </button>
      </div>

      {/* Add Word row */}
      <div className="flex items-center gap-2 px-1 py-0.5">
        <button
          data-testid="add-word-button"
          aria-pressed={addWordActive}
          onClick={onAddWordToggle}
          title="Toggle Add Word mode (Shift+A)"
          className={[
            "px-2 py-0.5 text-xs rounded border transition-colors",
            addWordActive
              ? "bg-green-500 text-white border-green-600 hover:bg-green-600"
              : "bg-white text-gray-700 border-gray-300 hover:bg-gray-50",
          ].join(" ")}
        >
          Add Word
        </button>
      </div>
    </div>
  );
}
