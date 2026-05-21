// QuickSearch.tsx — centred ⌘K search field in the header.
// P1.c (Gap 6): controlled input that filters the worklist by OCR/GT text.
// Task 5: wired to worklistStore.searchQuery.
//
// data-testids:
//   quick-search           — outer wrapper div
//   quick-search-input     — the <input> element
//   quick-search-keycap    — the ⌘K keycap chip button

import { useCallback } from "react";
import { useSyncExternalStore } from "react";
import { Search } from "@concavetrillion/pd-ui/icons";
import { dialogStore } from "../../stores/dialog-store";
import { worklistStore } from "../../stores/worklist-store";

function subscribeWorklist(cb: () => void) {
  return worklistStore.subscribe(cb);
}
function getWorklistSnapshot() {
  return worklistStore.getState();
}

export function QuickSearch() {
  const openHotkeyHelp = useCallback(() => {
    dialogStore.open("hotkeyHelp");
  }, []);
  const { searchQuery } = useSyncExternalStore(
    subscribeWorklist,
    getWorklistSnapshot,
    getWorklistSnapshot,
  );

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    worklistStore.setSearchQuery(e.target.value);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      worklistStore.setSearchQuery("");
      e.currentTarget.blur();
    }
  }

  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- cosmetic click-to-focus wrapper; the inner <input> is the real interactive element with full keyboard support
    <div
      data-testid="quick-search"
      className="flex items-center gap-1.5 h-7 px-2 rounded border border-border-2 bg-bg-sunk text-ink-3 min-w-[160px] max-w-[240px] w-full cursor-text"
      onClick={(e) => {
        const input = (e.currentTarget as HTMLElement).querySelector("input");
        input?.focus();
      }}
    >
      <Search size={11} aria-hidden="true" className="shrink-0 text-ink-3" />

      <input
        type="text"
        data-testid="quick-search-input"
        value={searchQuery}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder="Search…"
        aria-label="Quick search"
        className="flex-1 bg-transparent text-[11px] text-ink-2 placeholder:text-ink-3 focus:outline-none cursor-text"
      />

      <button
        type="button"
        data-testid="quick-search-keycap"
        aria-label="Show keyboard shortcuts (⌘K)"
        title="Show keyboard shortcuts"
        onClick={(e) => {
          e.stopPropagation();
          openHotkeyHelp();
        }}
        className="shrink-0 flex items-center gap-0.5 px-1 py-0.5 rounded border border-border-2 bg-bg-raised text-[9px] font-medium text-ink-3 hover:text-ink-1 hover:border-ink-3 transition-colors leading-none"
      >
        <span aria-hidden="true">⌘K</span>
      </button>
    </div>
  );
}
